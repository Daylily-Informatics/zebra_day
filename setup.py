from setuptools import setup, find_packages

setup(
    name='zebra_day',
    version='0.3.9.1',
    description='A Python library to manage a zebra printer fleet and an api for ZPL print requests.',
    author='John Major',
    author_email='john@daylilyinformatics.com',
    url='https://github.com/Daylily-Informatics/zebra_day',
    packages=find_packages(),
    install_requires=["yaml_config_day==0.0.5", "requests", "pytz==2023.3.post1", "cherrypy==18.8.0", "ipython==8.16.1", "pytest"],
    include_package_data=True,
    package_data={
        "zebra_day": [
            "bin/*",
            "etc/*",
            "etc/label_styles/*",
            "etc/label_styles/tmps/*",
            "etc/old_printer_config/*",
            "files/*",
            "static/*",
            "logs/*",
        ],
    },
    entry_points={
        "console_scripts": [
            "zday_quickstart = zebra_day.print_mgr:main",
            "zday_start = zebra_day.print_mgr:zday_start",
        ],
    },
)
