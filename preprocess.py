'''
Execute common tasks to files as extraction and secure conversion.
'''


import os
import shlex
import shutil
import zipfile
import logging
import datetime
import argparse
import subprocess
from concurrent import futures


from typing import (
    Union,
    List,
    Tuple,
    Generator,
)


def parse_args() -> argparse.Namespace:
    ''' Parse command line arguments '''

    parser = argparse.ArgumentParser()

    proc_opt = parser.add_argument_group('Parallel Tasks')
    proc_opt.add_argument('--max-workers',
                          help='Define the maximum number of parallel tasks.',
                          type=int)

    proc_opt.add_argument('--max-pdf-workers',
                          help='Define the maximum number of parallel pdf tasks.',
                          type=int)

    proc_opt.add_argument('--max-img-workers',
                          help='Define the maximum number of parallel image tasks.',
                          type=int)

    zip_opt = parser.add_argument_group('Zip Files')
    zip_opt.add_argument('-u',
                         '--keep-original-zip',
                         action='store_true',
                         help='Configure extractor to do not remove file after '
                         'extraction.')

    zip_opt.add_argument('--skip-zip',
                         action='store_true',
                         help='Do not unzip any file.')

    pdf_opt = parser.add_argument_group('Pdf files')

    pdf_opt.add_argument('--skip-pdf',
                         action='store_true',
                         help='Do not convert pdf files')

    pdf_opt.add_argument('--pdf-bin-converter',
                         type=str,
                         help='Path to custom pdf converter binary')

    img_opt = parser.add_argument_group('Image files')

    img_opt.add_argument('--skip-img',
                         action='store_true',
                         help='Do not convert image files')

    img_opt.add_argument('--img-bin-converter',
                         type=str,
                         help='Path to custom img converter binary')

    parser.add_argument('-v',
                        '--verbose',
                        help='Configure logging facility to display debug messages.',
                        action='store_true')

    parser.add_argument('directory', help='Source directory where u.sync books '
                        'had been stored.')

    return parser.parse_args()


def expose_files(directory: str, predicate: callable) -> Generator:
    ''' Scan all the files in given directory that matches some pattern '''

    with os.scandir(directory) as scan:
        for entry in scan:
            logging.debug('scanned dir entry: %s', entry)
            if entry.is_file() and predicate(entry.path) is True:
                logging.debug('found file: %s', entry)
                yield entry
            elif entry.is_dir():
                yield from expose_files(entry.path, predicate)


def unzip(path: str, flush: bool = True) -> None:
    ''' Perform extraction operation on target path removing file when needed '''

    logging.debug('extracting zip file: %s', path)
    with zipfile.ZipFile(path) as zip_reader:
        zip_reader.extractall(os.path.dirname(path))

    if flush:
        logging.debug('zip file will be removed: %s', os.path.basename(path))
        os.unlink(path)


def is_mimetype(path: str, *mimes) -> bool:
    ''' Check wheter a given file is of given mime type '''

    command = f'/usr/bin/file --mime-type {shlex.quote(path)}'
    logging.debug('executing command: %s', command)
    output = subprocess.check_output(shlex.split(command)).decode()
    logging.debug('file info output: %s', output)
    return any(mime in output for mime in mimes)


def check_cmd(command: str) -> bool:
    ''' Base function for running binaries '''

    try:
        logging.debug('executing command: %s', command)
        return subprocess.check_call(shlex.split(command)) == 0
    except subprocess.CalledProcessError:
        return False


def find_missing_packages(service_options: dict) -> List[str]:
    ''' Return packages where binaries are missing on file system '''

    missing = []
    for service, options in service_options.items():
        if options['no_check']:
            logging.debug('skipping binary check on service: %s', service)
        else:
            logging.debug('checking tool for service: %s', service)
            if not os.path.exists(options['bin']):
                missing.append(options['package'])
    return missing


def check_binaries(service_options: dict) -> bool:
    ''' Verify wheter all tools is available on system '''

    faileds = find_missing_packages(service_options)
    if faileds:
        header = 'some tools are not available on system:'
        log_list(header, faileds)
        logging.warning("please fix this, just because I won't let you continue from here")
        return False
    return True


def log_list(header: str, content: list) -> None:
    ''' Helper function for logging a list '''

    placeholder = [' - %s' for _ in content]
    logging.warning('\n'.join([header] + placeholder), *content)


def execute_converter(binary: str, *arguments: list) -> bool:
    ''' Check the converter exit code of service binary '''

    command = f'{binary} {" ".join(shlex.quote(arg) for arg in arguments)}'
    logging.debug('starting conversion: %s', arguments[0])
    return check_cmd(command)


def handle_futures(future_to_service: dict) -> None:
    ''' Helper function for waiting future results '''

    for future in futures.as_completed(future_to_service):
        stopped_service = future_to_service[future]
        result, error = None, None
        try:
            result = future.result()
        except Exception as exception:  # pylint: disable=broad-except
            error = exception
        yield (stopped_service, result, error)


def wait_futures(worker: callable,
                 services: list,
                 *args,
                 **executor_kwargs) -> List[str]:
    '''Manage parallel tasks with nice logging '''

    index, faileds, services_count = 0, [], len(services)
    with futures.ThreadPoolExecutor(**executor_kwargs) as executor:
        future_to_service = {executor.submit(worker, service, *args): service
                             for service in services}
        for service, success, error in handle_futures(future_to_service):
            if error:
                logging.error('%s exited with: %s', service, error)
            else:
                logging.debug('%s resulted in: %s', service, success)

            if not success:
                faileds.append(service)

            index += 1
            logging.info('fineshed: %s success: %s status: %s',
                         service,
                         success,
                         f'{index}/{services_count}')
    return faileds


def display_status(name: str, total: int, items_failed: list) -> None:
    ''' Helper function to display a nice overview about execution facts '''

    failure = len(items_failed)
    succeeded = total - failure
    proportion_of_success = (succeeded * 100) / total
    if failure:
        log_list(f'some items for {name} service have failed:', items_failed)
    logging.info('%s conversion done. succeeded: %d failure: %d ratio: %d%%',
                 name,
                 succeeded,
                 failure,
                 proportion_of_success)


def service_runner(worker: callable,
                   options: dict,
                   name: str,
                   directory: str,
                   **executor_kwargs) -> Union[None, Tuple[int, List[str]]]:
    ''' Scan targeted files in directory and try to convert them in parallel '''

    # unpack predicate options
    pred_func = options['predicate']['func']
    pred_args = options['predicate']['args']
    pred_kwargs = options['predicate']['kwargs']

    predicate = lambda f: pred_func(f, *pred_args, **pred_kwargs)
    items = [entry.path for entry in expose_files(directory, predicate)]
    if items:
        items_count = len(items)
        logging.debug('%s files found: %d', name, items_count)
        failed_items = wait_futures(worker, items, options, **executor_kwargs)
        return (items_count, failed_items)
    return None


def chained_foreground_run(services: list,
                           next_run: callable,
                           *run_args,
                           **run_kwargs) -> None:
    ''' Execute services in a chain in the incoming order. After all services are
        done calls next_run callable. '''

    def callback(_):
        if not services:
            logging.debug('no more services on foreground, calling next run...')
            next_run(*run_args, **run_kwargs)
        else:
            logging.debug('calling next service: %s', services[0])
            chained_foreground_run(services, next_run, *run_args, **run_kwargs)

    if not services:
        callback(None)
        return

    logging.debug('running on foreground: %s', services)
    args, kwargs = services.pop(0)

    with futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(service_runner, *args, **kwargs)
        future.add_done_callback(callback)
        display_service_futures({future: args[2]})


def background_run(services: list, max_workers: int = None) -> None:
    ''' Execute services in parallel '''

    if not services:
        logging.info('any available service to run in background, aborting...')
        return

    # by default, allocate 2 thread for each service
    if max_workers is None:
        max_workers = len(services)

    logging.debug('starting background run for services: %s', services)

    with futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_service = {executor.submit(service_runner, *args, **kwargs): args[2]
                             for args, kwargs in services}
        display_service_futures(future_to_service)


def display_service_futures(future_to_service: dict):
    ''' Helper function to display fineshed services '''

    for service, result, error in handle_futures(future_to_service):
        if error:
            logging.error('%s service exited with: %s', service, error)
        elif result:
            display_status(service, *result)
        else:
            logging.info('no %s files found', service)

        logging.info('service fineshed: %s', service)


def run_pdfs(path: str, options: dict) -> bool:
    ''' Safely convert UNTRUSTED pdf to TRUSTED '''

    return execute_converter(options['bin'], path)


def ensure_untrusted_images_dir(options: dict) -> None:
    ''' Create default directory for untrusted images when missing '''

    untrusted_imgs_dir = os.path.expanduser(options['kwargs']['untrusted_dir'])

    if not os.path.isdir(untrusted_imgs_dir):
        logging.debug('creating untrusted images directory at: %s',
                      untrusted_imgs_dir)
        os.mkdir(untrusted_imgs_dir)


def run_images(path: str, options: dict) -> bool:
    ''' Safely convert UNTRUSTED image to TRUSTED '''

    dest_path = os.path.dirname(path)
    dest_name = os.path.basename(path)
    dest_ext = os.path.splitext(dest_name)[1]
    dest = os.path.join(dest_path,
                        dest_name.replace(dest_ext, f'.trusted{dest_ext}'))

    result = execute_converter(options['bin'], path, dest)
    if result:
        logging.debug('moving old image to default directory: %s', path)
        shutil.move(path, options['kwargs']['untrusted_dir'])
    return result


def run_zips(path: str, options: dict) -> bool:
    ''' Unzip the archive on path '''

    unzip(path, flush=options['kwargs']['flush'])
    return True


def _map_service(name: str,
                 directory: str,
                 options: dict,
                 foregrounds: list,
                 backgrounds: list) -> None:
    ''' Helper function to map a service option to correct list '''

    args = [options['worker'], options, name, directory]
    kwargs = options['executor_kwargs']
    service_list = backgrounds if options['background'] else foregrounds
    service_list.append((args, kwargs))


def run_services(cli_args: argparse.Namespace, service_options: dict) -> None:
    ''' Call all services in using a specific execution flow '''

    directory = cli_args.directory

    background_services, foreground_services = [], []

    for service, options in service_options.items():
        if options['should_skip']:
            logging.info('skipping service: %s', service)
        else:
            options_copy = options.copy()
            _map_service(service,
                         directory,
                         options_copy,
                         foreground_services,
                         background_services)

            for hook in options['hooks']:
                hook_name = getattr(hook, '__name__', str(hook))
                logging.debug('%s executing hook: %s', service, hook_name)
                hook(options_copy)

    sort_func = lambda args: args[0][1].get('priority') or 0
    foreground_services.sort(key=sort_func, reverse=True)
    chained_foreground_run(foreground_services,
                           background_run,
                           background_services,
                           max_workers=cli_args.max_workers)



def setup_logging(verbose: bool) -> None:
    ''' Basic configuration of logging facility '''

    log_format = ['%(asctime)s', '-', '[%(levelname)s]', '%(message)s']
    if verbose:
        log_format.insert(1, '%(funcName)s')
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(format=' '.join(log_format), level=level)
    logging.getLogger(__file__)


def get_option_template(**kwargs) -> dict:
    ''' Helper function that returns the default options for some service '''

    return {
        # changes execution flow
        'should_skip': kwargs.get('should_skip', False),
        'no_check': kwargs.get('no_check', False),
        'package': kwargs.get('package'),
        'priority': kwargs.get('priority', 0), # only used when not background
        'background': kwargs.get('background', True),

        # task config
        'worker': kwargs.get('worker'),
        'bin': kwargs.get('binary'),
        'predicate': kwargs.get('predicate', get_predicate_template(None)),
        'kwargs': kwargs.get('kwargs', {}),
        'executor_kwargs': kwargs.get('executor_kwargs', {}),

        # hooks (executed before run in the order their appear)
        'hooks': kwargs.get('hooks', []),
    }


def get_predicate_template(func: callable, *args, **kwargs) -> dict:
    ''' Helper function to predicate service options '''

    return {
        'func': func,
        'args': args,
        'kwargs': kwargs,
    }


def pdf_options(**kwargs) -> dict:
    ''' Return default pdf service options '''

    predicate = get_predicate_template(is_mimetype, 'application/pdf')

    opt_kwargs = dict(worker=run_pdfs,
                      predicate=predicate,
                      package='qubes-pdf-converter',)

    opt_kwargs['should_skip'] = kwargs.get('skip_pdf')
    opt_kwargs['binary'] = kwargs.get('pdf_bin_converter') or '/usr/bin/qvm-convert-pdf'

    opt_kwargs['executor_kwargs'] = {
        'max_workers': kwargs.get('max_pdf_workers'),
    }

    return get_option_template(**opt_kwargs)


def image_options(**kwargs) -> dict:
    ''' Return default image service options '''

    predicate = get_predicate_template(is_mimetype, 'image/png', 'image/jpeg')

    opt_kwargs = dict(worker=run_images,
                      predicate=predicate,
                      package='qubes-img-converter',
                      hooks=[ensure_untrusted_images_dir],)

    opt_kwargs['should_skip'] = kwargs.get('skip_img')
    opt_kwargs['binary'] = kwargs.get('img_bin_converter') or '/usr/bin/qvm-convert-img'


    opt_kwargs['kwargs'] = {
        'untrusted_dir': kwargs.get('untrusted_dir') or '~/QubesUntrustedIMGs'
    }

    opt_kwargs['executor_kwargs'] = {
        'max_workers': kwargs.get('max_img_workers'),
    }

    return get_option_template(**opt_kwargs)


def zip_options(**kwargs) -> dict:
    ''' Return default zip service options '''

    predicate = get_predicate_template(zipfile.is_zipfile)

    opt_kwargs = dict(worker=run_zips,
                      predicate=predicate,
                      no_check=True,
                      background=False,
                      priority=100,)

    opt_kwargs['should_skip'] = kwargs.get('skip_zip')
    opt_kwargs['kwargs'] = {
        'flush': not kwargs.get('keep_original_zip'),
    }

    return get_option_template(**opt_kwargs)


def gen_service_options(**kwargs) -> dict:
    ''' Generate a control dictionary about how services will run '''

    return {
        'pdf': pdf_options(**kwargs),
        'image': image_options(**kwargs),
        'zip': zip_options(**kwargs),
    }


def init() -> Tuple[dict, dict]:
    ''' Inialize arguments and generate service mapping '''

    cli_args = parse_args()
    setup_logging(cli_args.verbose)
    logging.debug('arguments from cli: %s', cli_args)
    return (cli_args, gen_service_options(**vars(cli_args)))


def precheck(service_options: dict) -> Union[int, None]:
    ''' Make all checks on services and return an exit code '''

    available_checks = [check_binaries]
    if not all(check(service_options) for check in available_checks):
        return 127

    return None


def main() -> int:
    ''' Entry point function '''

    cli_args, service_options = init()
    start_time = datetime.datetime.now()

    logging.debug('service options: \n%s', service_options)

    pre_check_result = precheck(service_options)
    if pre_check_result is not None:
        return pre_check_result

    run_services(cli_args, service_options)

    logging.info('execution time: %s', datetime.datetime.now() - start_time)
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
