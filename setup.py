'''
Main distribution file.
'''


from distutils.core import setup


setup(name='qubes-app-usync',
      version='0.1.0',
      description='Convert untrusted pdf and images in parallel from u.sync files',
      license='BSD 3-Clause',
      author='Yan Marques de Cerqueira',
      author_email='marques_yan@outlook.com',
      py_modules=[
          'preprocess',
      ],
      scripts=[
          'qubes.Download',
      ],
      keywords='u.sync, qubes, security, pdf, png, jpeg',
      classifiers=[
          'Development Status :: 1 - Beta',
          'Environment :: Console',
          'Intended Audience :: Education',
          'Intended Audience :: End Users/Desktop',
          'Operating System :: POSIX',
          'Operating System :: Unix',
          'License :: OSI Approved :: BSD License',
          'Programming Language :: Unix Shell',
          'Programming Language :: Python :: 3.5',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Programming Language :: Python :: 3.8',
          'Topic :: Security',
      ])
