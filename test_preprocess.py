'''
Functional test of preprocess module.
'''


import os
import pathlib
import secrets
import zipfile
import subprocess
import concurrent.futures
from unittest import mock

import pytest
import preprocess


@pytest.fixture
def custom_mimetype(monkeypatch):
    ''' Replace function used by preprocess.is_mimetype to return arbitrary output '''

    def monkey(return_value: str):
        my_check_output = lambda *args, **kwargs: return_value.encode()
        monkeypatch.setattr(subprocess, 'check_output', my_check_output)
    return monkey


@pytest.fixture
def zip_factory(tmp_path, monkeypatch):
    ''' Generate a directory with zipped files '''

    target_file = tmp_path / pathlib.Path('foo.zip')
    with zipfile.ZipFile(target_file, mode='w') as _:
        pass

    fake_zipfile = mock.MagicMock()

    # the variable will be called as function and also by the context manager,
    # but by default it returns another mock object, but we do not want to lose
    # the object reference. For that to happen, this trick makes the mock return
    # itself when called or when entered the context.
    fake_zipfile.return_value = fake_zipfile
    fake_zipfile.__enter__.return_value = fake_zipfile

    monkeypatch.setattr(zipfile, 'ZipFile', fake_zipfile)
    yield (tmp_path, fake_zipfile, target_file)

    if target_file.exists():
        target_file.unlink()


@pytest.fixture
def bin_services_factory(tmp_path):
    ''' Return a factory for fake binaries '''

    def factory(index: int = 0):
        binaries = [tmp_path / pathlib.Path('foo'),
                    tmp_path / pathlib.Path('bar'),]

        service_args = {
            'pdf_bin_converter': binaries[0],
            'img_bin_converter': binaries[1],
        }

        for binary in binaries[index:]:
            with open(binary, 'w') as _:
                pass

        return preprocess.gen_service_options(**service_args)
    return factory


# pylint: disable=missing-function-docstring,redefined-outer-name


def test_scanned_files(tmp_path):
    last_dir = tmp_path
    choosen = []

    # create a nested tree
    for _ in range(5):
        new_file = pathlib.Path(secrets.token_hex(6))
        if secrets.choice([True, False]) or not choosen:
            choosen.append(new_file)

        with open(last_dir / new_file, 'w') as _:
            pass

        last_dir = last_dir / pathlib.Path(secrets.token_hex(6))
        os.mkdir(last_dir)

    for entry in preprocess.expose_files(str(tmp_path), lambda f: f in choosen):
        assert entry.name in choosen, 'invalid scanned file found'


def test_verifying_one_mimetype(custom_mimetype):
    mime = 'foo'
    custom_mimetype(mime)
    assert preprocess.is_mimetype('bar', mime), 'mimetype verification failed for one target'


def test_verifying_many_mimetypes(custom_mimetype):
    mimes = ['bla', 'yada', 'foo',]
    custom_mimetype(mimes[1])
    assert preprocess.is_mimetype('bar', *mimes), 'mimetype verification failed for many targets'


def test_mimetype_verification_fails_on_invalid(custom_mimetype):
    mimes = ['bla', 'yada', 'baz',]
    custom_mimetype('foo')
    assert not preprocess.is_mimetype('bar', *mimes), 'mimetype asserted false when was true'


def test_unzip(zip_factory):
    tmp_path, zip_mock, zip_file = zip_factory

    preprocess.unzip(zip_file)

    zip_mock.assert_called_with(zip_file)
    zip_mock.extractall.assert_called_with(str(tmp_path))
    zip_mock.__enter__.assert_called()

    assert not zip_file.exists(), 'zip file was not removed'


def test_unzip_keeps_zipfiles(zip_factory):
    _, _, zip_file = zip_factory

    preprocess.unzip(zip_file, flush=False)
    assert zip_file.exists(), 'zip file were removed'


def test_check_binaries(bin_services_factory):
    options = bin_services_factory()
    result = preprocess.check_binaries(options)
    assert result, 'fake binaries failed to pass verification'


def test_find_missing_binaries(bin_services_factory):
    # only create binaries from index 1
    service_options = bin_services_factory(1)
    expected_missing = [list(service_options.values())[0]['package'],]

    faileds = preprocess.find_missing_packages(service_options)
    assert expected_missing == faileds, 'invalid missing packages found'


def test_execute_converter_escapes_shell_chars(monkeypatch):
    fake_binary = 'foo'
    fake_arguments = ['bar ; yada', 'baz',]
    expected_cmd = "foo 'bar ; yada' baz"

    check_cmd_mock = mock.Mock()
    monkeypatch.setattr(preprocess, 'check_cmd', check_cmd_mock)

    preprocess.execute_converter(fake_binary, *fake_arguments)
    check_cmd_mock.assert_called_with(expected_cmd)


def test_handle_futures(monkeypatch):
    services = [('foo', lambda: True),
                ('bar', RuntimeError),
                ('baz', lambda: 'yada'),]

    expected_result = [('foo', True, None),
                       ('bar', None, RuntimeError),
                       ('baz', 'yada', None),]

    future_to_service = {}
    for name, effect in services:
        future_mock = mock.Mock()
        future_mock.result.side_effect = effect
        future_to_service[future_mock] = name

    monkeypatch.setattr(concurrent.futures,
                        'as_completed',
                        mock.Mock(return_value=future_to_service.keys()))

    result_gen = preprocess.handle_futures(future_to_service)
    assertion_msg = '%s from future differs from expected'

    for service, result, error in expected_result:
        past_service, past_result, past_error = next(result_gen)
        assert service == past_service, assertion_msg % 'service'
        assert result == past_result, assertion_msg % 'result'
        if past_error:
            assert isinstance(past_error, error), assertion_msg % 'exception instance'
        else:
            assert past_error == error, assertion_msg % 'error'


def _dump_equal(item1, item2):
    return item1 == item2


def test_wait_futures():
    items = ['foo', 'baz',]
    expected_faileds = ['baz',]

    faileds = preprocess.wait_futures(_dump_equal, items, 'foo')

    assert expected_faileds == faileds


def _foo_worker(item, options):
    return options['predicate']['func'](item, options['match'])


def test_service_runner(tmp_path):
    def predicate(path, *items):
        return any(path.endswith(item) for item in items)

    target_files = []

    for i in range(3):
        target_file = tmp_path / pathlib.Path(str(i))
        with open(target_file, 'w') as _:
            pass
        target_files.append(str(target_file))

    # filter files, only get 0 and 1
    options = preprocess.get_predicate_template(predicate, '0', '1')

    # worker will succeeded when file matches the match option
    result = preprocess.service_runner(_foo_worker,
                                       dict(predicate=options, match='0'),
                                       'foo',
                                       str(tmp_path))

    assert result[0] == 2, 'invalid number of files targeted'
    assert target_files[1:2] == result[1], 'worker returned true when was false'


def test_chained_foreground_run(monkeypatch):
    services, service_calls = [], []

    for i in range(3):
        service_args = ([i] * 3, {'yada': i})
        services.append(service_args)
        call = mock.call(*service_args[0], **service_args[1])
        service_calls.append(call)

    # create a mock with arbitrary return
    service_mock = done_mock = mock.Mock(return_value=(1, []))
    run_args, run_kwargs = 'foo', {'bar': 'baz'}

    service_calls.append(mock.call(run_args, **run_kwargs))

    monkeypatch.setattr(preprocess, 'service_runner', service_mock)
    preprocess.chained_foreground_run(services, done_mock, run_args, **run_kwargs)
    service_mock.assert_has_calls(service_calls, any_order=False)


def test_chained_foreground_run_with_no_service():
    # create a mock with arbitrary return
    done_mock = mock.Mock()

    preprocess.chained_foreground_run([], done_mock)
    done_mock.assert_called_with()


def test_ensure_untrusted_images_dir(tmp_path):
    target_dir = tmp_path / pathlib.Path('bar')
    options = dict(kwargs=dict(untrusted_dir=target_dir))
    preprocess.ensure_untrusted_images_dir(options)
    assert target_dir.is_dir(), 'untrusted directory is not valid'


def test_run_images(tmp_path, monkeypatch):
    for return_value in [True, False,]:
        target_file = tmp_path / pathlib.Path(secrets.token_hex(6))
        untrusted_dir = tmp_path / pathlib.Path(secrets.token_hex(6))
        move_target = untrusted_dir / pathlib.Path(target_file.name)
        options = preprocess.image_options(untrusted_dir=untrusted_dir)

        with open(target_file, 'w') as _:
            pass

        os.mkdir(untrusted_dir)
        exec_mock = mock.Mock(return_value=return_value)
        monkeypatch.setattr(preprocess, 'execute_converter', exec_mock)

        result = preprocess.run_images(str(target_file), options)

        assert result is return_value
        assert target_file.exists() is not return_value
        assert move_target.exists() is return_value


def test_run_services(monkeypatch):
    cli_args = mock.Mock()
    cli_args.directory.return_value = 'foo'
    cli_args.max_workers.return_value = 123

    hook_mock = mock.Mock()
    hooks = [hook_mock,]

    options = {
        'foo': preprocess.get_option_template(background=False),
        'bar': preprocess.get_option_template(background=False, priority=1),
        'baz': preprocess.get_option_template(hooks=hooks),
        'skipped': preprocess.get_option_template(should_skip=True, hooks=hooks),
    }

    expected_fg_services, expected_bg_services = [], []

    for service in ['bar', 'foo', 'baz',]:
        # pylint: disable=protected-access
        preprocess._map_service(service,
                                cli_args.directory,
                                options[service],
                                expected_fg_services,
                                expected_bg_services)

    run_mock = mock.Mock()
    monkeypatch.setattr(preprocess, 'chained_foreground_run', run_mock)
    preprocess.run_services(cli_args, options)

    hook_mock.assert_called_once()
    run_mock.assert_called_with(expected_fg_services,
                                preprocess.background_run,
                                expected_bg_services,
                                max_workers=cli_args.max_workers)
