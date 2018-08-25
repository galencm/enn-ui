# enn-ui

## Installation

Pip:

```
pip3 install git+https://github.com/galencm/enn-ui --user --process-dependency-links
```

Develop while using pip:

```
git clone https://github.com/galencm/enn-ui
cd enn-ui/
pip3 install --editable ./ --user --process-dependency-links
```

## Usage

**enn-dev**

_discover and configure devices_

```
enn-dev --size=1500x800 -- --db-port 6379 --db-host 127.0.0.1
```

**enn-db**

_load device configurations (such as chdk propsets) into the database to be used by `enn-dev`_

```
enn-db --db-port 6379 --db-host 127.0.0.1
```

**enn-env**

_view and modify machinic light environment values_

```
enn-env --size=1500x800 -- --db-port 6379 --db-host 127.0.0.1
```

## Contributing
This project uses the C4 process 

[https://rfc.zeromq.org/spec:42/C4/](https://rfc.zeromq.org/spec:42/C4/
)

## License
Mozilla Public License, v. 2.0

[http://mozilla.org/MPL/2.0/](http://mozilla.org/MPL/2.0/)

