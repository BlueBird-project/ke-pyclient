# KE PYClient (ke-pyclient)

Python client for TNO Knowledge Engine

## Library management

### build

``` 
poetry config repositories.github https://pypi.pkg.github.com/BlueBird-project
poetry config pypi-token.github <token>

 poetry publish --build -r github
```

### install

```
pip install git+https://github.com/BlueBird-project/ke-pyclient.git
```
