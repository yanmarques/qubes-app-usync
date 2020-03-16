===========
Qubes Usync
===========

These qubes script allows one to integrate
`u.sync <https://github.com/computacaoUnisul/u.sync>`__ synchronization
with Qubes image and pdf converters. It consists of a python module for
file pre-processing and a shell script that calls u.sync package. For
now, u.sync package has a bad structure and also mus be executed with
shell script, and while it is not changed, to work around this I created
a
`Makefile <https://github.com/yanmarques/qubes-app-usync/blob/master/Makefile>`__
to automatically build it and make available for this package.

**This package still need more testing and adjustments (bug fixing).
Although feel free to use and test it.**

Getting started
---------------

Installation
~~~~~~~~~~~~

-  python versions tested:

   -  3.6
   -  3.7
   -  3.8

   *it*\ **may**\ *(or may*\ **not**\ *) work in older versions
   of*\ **python3**

1. download methods:

   -  cloning:

   .. code:: bash

      $ git clone git@github.com:yanmarques/qubes-app-usync.git

   -  `download <https://github.com/yanmarques/qubes-app-usync/archive/master.zip>`__

2. build u.sync, you have to make sure ``make`` is installed, then:

.. code:: bash

   $ make

That is it!
'''''''''''

Run
~~~

Preprocessing files and copying them to another qube requires a few
utilities installed. These requirements are easily installed using
package managers.

Requirements
^^^^^^^^^^^^

-  qubes-core-agent-linux
-  qubes-pdf-converter
-  qubes-img-converter

The main script is
`qubes.Download <https://github.com/yanmarques/qubes-app-usync/blob/master/qubes.Download>`__.
It will simply call u.sync package with some default options: - keep
account online (cookies will be stored locally) - download files to a
timestamped temporary directory ending with ``-sync``

Then it will pre-process these downloaded files with
`preprocess.py <https://github.com/yanmarques/qubes-app-usync/blob/master/preprocess.py>`__.
Arguments passed to qubes.Download will go to preprocess.py script,
these arguments are:

::

   usage: preprocess.py [-h] [--max-workers MAX_WORKERS]
                        [--max-pdf-workers MAX_PDF_WORKERS]
                        [--max-img-workers MAX_IMG_WORKERS] [-u] [--skip-zip]
                        [--skip-pdf] [--pdf-bin-converter PDF_BIN_CONVERTER]
                        [--skip-img] [--img-bin-converter IMG_BIN_CONVERTER] [-v]
                        directory

   positional arguments:
     directory             Source directory where u.sync books had been stored.

   optional arguments:
     -h, --help            show this help message and exit
     -v, --verbose         Configure logging facility to display debug messages.

   Parallel Tasks:
     --max-workers MAX_WORKERS
                           Define the maximum number of parallel tasks.
     --max-pdf-workers MAX_PDF_WORKERS
                           Define the maximum number of parallel pdf tasks.
     --max-img-workers MAX_IMG_WORKERS
                           Define the maximum number of parallel image tasks.

   Zip Files:
     -u, --keep-original-zip
                           Configure extractor to do not remove file after
                           extraction.
     --skip-zip            Do not unzip any file.

   Pdf files:
     --skip-pdf            Do not convert pdf files
     --pdf-bin-converter PDF_BIN_CONVERTER
                           Path to custom pdf converter binary

   Image files:
     --skip-img            Do not convert image files
     --img-bin-converter IMG_BIN_CONVERTER
                           Path to custom img converter binary
