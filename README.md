# KE PYClient (ke-pyclient)

Python client for TNO Knowledge Engine

## Library management

### build

``` 
poetry config repositories.github https://pypi.pkg.github.com/BlueBird-project
poetry config pypi-token.github <token>

 poetry publish --build -r github
```

### Install

#### requirements.txt

template:

```text
git+https://github.com/BlueBird-project/ke-pyclient.git@v${VERSION} 
ke_client==${VERSION} 
```

for VERSION=0.18.9

```text 
git+https://github.com/BlueBird-project/ke-pyclient.git@v0.18.9
ke_client==0.18.9
```

list of published versions: [here](https://github.com/BlueBird-project/ke-pyclient/tags)

```
pip install git+https://github.com/BlueBird-project/ke-pyclient.git
```
 


OLD:
```
-i  https://__token__:glpat-ImK7hy9M8LSfcyRsGTCbi286MQp1OjFmNAk.01.0z15f6qqh@gitlab.pcss.pl/api/v4/projects/2735/packages/pypi/simple
ke_client==0.5.15
```
Add extra index to the client repository
``` 
--extra-index-url https://__token__:glpat-ImK7hy9M8LSfcyRsGTCbi286MQp1OjFmNAk.01.0z15f6qqh@gitlab.pcss.pl/api/v4/projects/2735/packages/pypi/simple

```
install
``` 
pip install ke_client==0.16.1
```
