from setuptools import find_packages, setup

setup(
    name="enn_ui",
    version="0.1",
    description="",
    author="Galen Curwen-McAdams",
    author_email="",
    platforms=["any"],
    license="Mozilla Public License 2.0 (MPL 2.0)",
    include_package_data=True,
    data_files=[("", ["LICENSE.txt", "enn_ui/reference.xml"])],
    url="",
    packages=find_packages(),
    install_requires=[
        "kivy",
        "ma_cli",
        "lings",
        "keli",
        "pyudev",
        "fold_ui",
        "pre-commit",
    ],
    dependency_links=[
        "https://github.com/galencm/ma-cli/tarball/master#egg=ma_cli-0.1",
        "https://github.com/galencm/machinic-keli/tarball/master#egg=keli-0.1",
        "https://github.com/galencm/machinic-lings/tarball/master#egg=lings-0.1",
        "https://github.com/galencm/fold-lattice-ui/tarball/master#egg=fold_ui-0.1",
    ],
    entry_points={
        "console_scripts": [
            "ma-ui-enn = enn_ui.enn_ui:main",
            "enn-dev = enn_ui.dev_ui:main",
            "enn-db = enn_ui.reference:main",
            "enn-env = enn_ui.env_ui:main",
        ]
    },
)
