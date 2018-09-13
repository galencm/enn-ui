# Contributing

This project uses:

* MPL v2.0 license

This project follows:

* the C4 process
* code style guidelines
* optimistic merging

Contributions that meet the C4 patch requirements and code style guidelines below should be optimistically merged.

C4:

[Collective Code Construction Contract](https://rfc.zeromq.org/spec:42/C4/
)

Code Style Guidelines:

* Commit Messages
    
    A commit or patch identifies a problem and offers a solution. The commit message follows the form:

    ```
    Problem:...

    Solution:...
    ```

    or if additional context is needed:

    ```
    Problem:...

    some explanatory or context lines between blanklines

    Solution:...
    ```

    The title line no more than 50 chars and body lines around 60 chars. A blankline separates the _Problem:_ and _Solution:_ lines. 
* Python

    Python code is formatted with `black` and linted with `flake8`.  Flake8 uses a black-compatible configuration file `.flake8` in the projects toplevel directory. All black defaults are used. 

    Setting up git commit hooks using `pre-commit` will format and lint both python code and commit messages on commit. There are instructions for setup in `README.md`. 

    Otherwise `black` and `flake8` can be run manually. For example:

    ```
    black file.py
    flake8 --config=.flake8 file.py
    ```

    links:

    * [black](https://github.com/ambv/black)
    * [flake8](https://github.com/pycqa/flake8)
    * [pre-commit](https://github.com/pre-commit)
* Shell Scripts

    To format use `beautysh` which modifies in place. To lint use `shellcheck`. For example:
    
    ```
    beautysh --file script.sh
    shellcheck script.sh
    ```

    links:

    * [beautysh](https://github.com/bemeurer/beautysh)
    * [shellcheck](https://github.com/koalaman/shellcheck)

Further Reading:

For more descriptions of C4 and the problem/solution approach, documentation from the zeromq community and some of its projects is helpful:

* [zeromq wiki](http://zeromq.org/docs:contributing)
* [czmq](https://github.com/zeromq/czmq/blob/master/CONTRIBUTING.md)
* [libzmq](https://github.com/zeromq/libzmq/blob/master/.github/PULL_REQUEST_TEMPLATE.md)

The git hooks/pre-commit configuration comes from:

* [Automate Python workflow using pre-commits: black and flake8](https://ljvmiranda921.github.io/notebook/2018/06/21/precommits-using-black-and-flake8/)
