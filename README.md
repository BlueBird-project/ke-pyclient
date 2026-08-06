# KE PYClient (ke-pyclient)

Python client for TNO Knowledge Engine

## BlueBird UBFlex
This library is used by the [UBFlex](https://github.com/BlueBird-project/UBFlex) integration layer in the BlueBird project. UBFlex contains BlueBird-specific ontology definitions, graph-pattern configurations, Smart Connector resources and integration documentation. `ke-pyclient` remains a separate reusable Python client library for the TNO Knowledge Engine."

## Library management

### build

``` 
poetry config repositories.github https://pypi.pkg.github.com/BlueBird-project
poetry config pypi-token.github <token>

 poetry publish --build -r github
```

### Install

#### requirements.txt

Add to the pip requirements file :

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

### Extending KI Graph pattern

**Only REACT and ANSWER**

**POST and ASK aren't extended** - adding one of those type new KI would require calling the same handler multiple
times.
Each handler call would result with new KI and potentially the same information could be sent to the client more than
once due to multiple separate KIs.
 