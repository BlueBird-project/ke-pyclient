# Getting started

- KE server docs [docs](https://docs.knowledge-engine.eu/) , [github](https://github.com/TNO/knowledge-engine)

- KE
  presentation [local](BlueBird-PMB-MP9-WP5-2025-09-23.pptx) , [sharepoint](https://gfi1.sharepoint.com/:p:/r/sites/Smart-gridreadyandsmart-networkreadybuildings/_layouts/15/Doc.aspx?sourcedoc=%7B1123754C-280A-4EE7-A547-AA6C17B65BDE%7D&file=BlueBird-PMB-MP9-WP5-2025-09-23.pptx&action=edit&mobileredirect=true)

- KE REST API [Swagger documentation](./openapi-sc.yaml)

- install [Install](../README.md#install)
 
- sample project with FM-TM interaction [link](https://github.com/BlueBird-project/ke-sample-client)

- Client Configuration [link](#configuration)
  - Graph patterns docs [link](#graph-patterns)
  - Bluebird graph patterns [repository](https://github.com/BlueBird-project/knowledge-interaction-config)
- Implementing the [python client](#python-client)
  - decorating [ki methods](#decorating-ki-methods)
  - KI data exchange [objects](#ki-objects)
## Glossary

- KI - Knowledge interation
- KE - Knowledge engine
-

## Configuration

### KE Server location

Provide address (*rest_end_point*) of existing remote KE server or [run docker](#run-knowledge-engine-docker)

Address template:

``` 
{protocol}://{host}:{port}/rest/
```

Example:

``` 
https://locahost:8280/rest/
```

### Knowledge base id

Knowledge base id (`knowledge_base_id`, _**str**_): client identifier, **must** be unique - currently there no security
or
protection from id spoofing mechanism.
(TODO: currently no plans to implement it, but if there will be enough efforts within the project it might be
implemented )

### Other Properties

- `config_path`(_**str**_) - graph pattern config file path

_(TODO: describe other config fields)_

### Configuring client

Client can be configured through loaded environmental variables, dotenv file (.env) or YAML config file.
Configuration source priorities:

1. Environmental variables (variable names prefixed with `KE_`, e.g. `REST_ENDPOINT` becomes `KE_REST_ENDPOINT`)
2. YAML file (section: `ke`)
3. Dotenv file (section: (variable names prefixed with `KE_`)

#### Loading config file

Client can be configured with **.yml** file:

```python
from ke_client import configure_ke_client

configure_ke_client(yml_config_path="config.yml")
```

Sample `config.yml` file:

```yaml 
#client section 'ke'
ke:
  #  knowledge_base_id: 
  #  rest_endpoint: 
  # ki_config_vars_path:  
  # reasoner_level: 1
  # ki_vars: 
  # graph pattern configuration file
  ki_config_path: src/config_files/fm_test.yml
```

### Graph patterns

#### Useful ontologies and prefixes

- rdf: "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
- xsd: "http://www.w3.org/2001/XMLSchema#"
- saref:
  - saref: "https://saref.etsi.org/core"
  - s4ener: "https://saref.etsi.org/saref4ener"
  - s4city: "https://saref.etsi.org/s4city"
- foaf: "http://xmlns.com/foaf/0.1/"
- time: "http://www.w3.org/2006/time#"
- ubmarket: "https://ubflex.bluebird.eu/market" todo: integrate with BIGG
- om: "http://www.ontology-of-units-of-measure.org/resource/om-2/CelsiusTemperatureUnit"

#### YAML config file description (*.yml):

General fields:

- `kb_description` - optional description of the client
- `kb_name` - it's required by the KE server, but the KE server might allow duplicate KB names in the system
- `graph_patterns` - dictionary of KI graphs use in the interactions between all clients registered to KE. The same
  pattern can be used for all kinds of knowledge interactions (ASK,POST,REACT,ANSWER).
  KE uses semantic reasoning over interactions and tries to match graph query ( ANSWER to ASK and REACT to POST  ) with
  the knowledge shared by the registered clients.
  clients.
- `prefixes` - list of prefixes included in all graphs

Graph patterns definition:

- `name` - unique name within the application
- `description` - optional description field
- `prefixes` - list of prefixes use in `pattern` and `result_pattern`
- `pattern` - rdf graph pattern representing available data
- `result_pattern` - graph pattern for REACT KI

##### Example:

```yaml
knowledge_engine:
  kb_name: "fm-test-client"
  kb_description: ""
  prefixes:
    kb: "${KB_ID}/"
    rdfs: "<http://www.w3.org/2000/01/rdf-schema#>"
    s4ener: "https://saref.etsi.org/saref4ener/"
  graph_patterns:
    fm-ts-info-request:
      name: "fm-ts-info-request"
      description: "Exchange information about the saref:timeseries. Recommended saref usage :
       s4ener:Consumption, s4ener:Downflex,   s4ener:Production,  s4ener:Upflex  "
      prefixes:
        xsd: "http://www.w3.org/2001/XMLSchema#"
        time: "http://www.w3.org/2006/time#"
        saref: "https://saref.etsi.org/core/"
      pattern:
        - ' <http://fm.test.bluebird.com>  rdf:type saref:Service . '
        - ' ?ts_interval_uri rdf:type time:Interval; time:hasBeginning ?ts_date_from; time:hasEnd ?ts_date_to .'
      result_pattern:
        - ' ?ts_uri rdf:type s4ener:TimeSeries ; s4ener:hasUsage ?ts_usage; '
        - ' s4ener:producedBy  <http://fm.test.bluebird.com> ; s4ener:hasUpdateRate "PT60M"^^xsd:duration ; '
        - ' s4ener:hasCreationTime ?time_create ; s4ener:hasEffectivePeriod ?ts_interval_uri .'


```

#### Reasoning

KE server uses semantic reasoning to match patterns (e.g. matching ASK pattern with ANSWER pattern ) in the system.
For example to get value from temperature sensor '<temperature-sensor-1>' we can use such KI graph patterns:

ANSWER KI pattern:

```text
     ?sensor rdf:type saref:Sensor . 
     ?measurement saref:measurementMadeBy <temperature-sensor-1> .
     ?measurement saref:isMeasuredIn saref:TemperatureUnit .
     ?measurement saref:hasValue ?value .
```  

ASK KI(1):

```text
?measurement saref:measurementMadeBy <temperature-sensor-1> . 
?measurement saref:hasValue ?value .
```

Binding set returned for the ASK KI(1):

```json lines
[
  ...,
  {
    "value": "\"12\"^^<http://www.w3.org/2001/XMLSchema#integer>",
    "measurement": "<https://test.bluebird.com/schema/posttest/measurement/662>"
  },
  ...
]
```

ASK KI(2):

```text
?measurement saref:measurementMadeBy <temperature-sensor-1> . 
?measurement saref:hasValue ?value .
?measurement saref:isMeasuredIn ?measurementUnit .
```

Binding set returned for the ASK KI(2):

```json lines
[
  ...,
  {
    "measurementUnit": "om:CelsiusTemperatureUnit",
    "value": "\"12\"^^<http://www.w3.org/2001/XMLSchema#integer>",
    "measurement": "<https://test.bluebird.com/schema/posttest/measurement/662>"
  },
  ...
]
```

## Python client

### Load custom configuration

```python
from ke_client import configure_ke_client

configure_ke_client(yml_config_path="config.yml")
```

### Init client instance

```python
from ke_client import KEClient

ki_client = KEClient.build()
```

### Decorating KI methods

```python
# `graph_name` - KI name 
@ki_client.post("graph_name")
def request_method(custom_arg, ...):
  ...
  #  Each returned POST graph binding set must use all graph variables  (e.g. '?sensor') defined in the KI's pattern 
  return [{"arg": "binding"}]  # List of binding sets
```

Calling defined POST KI:

```python
from ke_client.ki_model import KIPostResponse

data_bindings: KIPostResponse = request_method(custom_arg='', ...)

```

For KI responses  (REACT - subscribe to POST )

```python

@ki_client.react("graph_name")
def on_graph_name(ki_id: str, post_bindings: List[Dict[str, Any]]):
  ...
  # process post_bindings
  ...
  # return result_pattern bindings or empty list if result_pattern is empty
  return [{"arg": "binding"}] 
```

### Register

All KI's must be registered in KE, before running them.

```python
# all decorated methods have to be initialized before calling `register()`
ki_client.register()

``` 

### KI objects

#### Bindings object decorator  `ki_object`

`ki_object` - KI exchange object, it is responsible for naming integrity between bindings variables defined in the graph
pattern in the ki config file and python objects. All RDF's Uris should be of type rdflib.RDFUri. Other fields can be
either rdflib.Literal or standard type (e.g float, int )

```python
# standard graph pattern exchange object
@ki_object("fm-ts-info-request")
class FMTSRequest(BindingsBase):
  ts_interval_uri: URIRef
  ts_date_from: Literal
  ts_date_to: Literal
  some_float_value: float


# result graph pattern exchange object
@ki_object("fm-ts-info-request", result=True)
class FMTSResponse(BindingsBase):
  ts_uri: URIRef
  ts_interval_uri: URIRef
  # ts_usage: Union[Literal, URIRef]
  ts_usage: URIRef
  time_create: Literal


# allow subset of graph's pattern bindings arguments (useful for ASK KI)
@ki_object("fm-ts-info-request", allow_partial=True)
class FMTSRequest(BindingsBase):
  ts_date_from: Literal
  ts_date_to: Literal


```

`split_uri` - object to manage RDFUris patterns in order to meet data filtering requirements (uris can encode some
filters ) and unify the Uris templates.

For example encoding timeseries time span (start '_ts_' and duration '_period_minutes_')):

```python
from ke_client import SplitURIBase

kb_id = "http://tm.example.org"


@ki_split_uri(uri_template=f"{kb_id}/tou" + "/${range_id}/${period_minutes}/${ts}")
class TOUSplitURI(SplitURIBase):
  range_id: int
  period_minutes: int
  ts: int

```
 
 