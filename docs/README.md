# Getting started

- KE server docs [docs](https://docs.knowledge-engine.eu/) , [github](https://github.com/TNO/knowledge-engine)

- KE
  presentation [local](BlueBird-PMB-MP9-WP5-2025-09-23.pptx) , [sharepoint](https://gfi1.sharepoint.com/:p:/r/sites/Smart-gridreadyandsmart-networkreadybuildings/_layouts/15/Doc.aspx?sourcedoc=%7B1123754C-280A-4EE7-A547-AA6C17B65BDE%7D&file=BlueBird-PMB-MP9-WP5-2025-09-23.pptx&action=edit&mobileredirect=true)

- KE REST API [Swagger documentation](./openapi-sc.yaml)
 
- install [Install](../README.md#install)
- 
- sample project [link](https://github.com/BlueBird-project/ke-sample-client)

- Configuration [link](#configuration)
  - Graph patterns docs [link](#graph-patterns)
  - Bluebird graph patterns [repository](https://github.com/BlueBird-project/knowledge-interaction-config)

## Glossary

- KI - Knowledge interation
- KE - Knowledge engine
- 


## Configuration

### KE Server location

provide address (*KE_REST_ENDPOINT*) of existing KE server or [run docker](#run-knowledge-engine-docker)

Address template:

``` 
{protocol}://{host}:{port}/rest/
```

Example:

``` 
https://locahost:8280/rest/
```

### Knowledge base id

Knowledge base id (*knowledge_base_id*) **must** be unique - currently it's not secured or protected from id spoofing

### Graph patterns

##### useful prefixes

- rdf: "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
- xsd: "http://www.w3.org/2001/XMLSchema#"
- saref: 
  - saref: "https://saref.etsi.org/core"
  - s4ener: "https://saref.etsi.org/saref4ener"
  - s4city: "https://saref.etsi.org/s4city"
- foaf: "http://xmlns.com/foaf/0.1/"
- time: "http://www.w3.org/2006/time#"
- ubmarket: "https://ubflex.bluebird.eu/market"

        
#####
Set path to graph pattern file (*KE_KI_CONFIG_PATH*)
Sample files: [1](./example/test_ke_client/ke_config_post.yml),[2](./example/test_ke_client/ke_config_react.yml)

YAML config file description (*.yml):

- kb_description - optional description of the client
- kb_name - it's required by the KE server, but the KE server might allow duplicate KB names in the system
- knowledge_base_id - unique client identifier, it's uniqueness across clients isn't checked by KE server itself
- graph_patterns - dictionary of KI graphs - here you can define graphs with prefixes.
  The same pattern can be used for all kinds of knowledge interactions (ASK,POST,REACT,ANSWER).
  KE uses semantic reasoning over interactions and tries to match graph query to the knowledge shared by the other
  clients.  
  In the exemplary project ASK and ANSWER interactions are the same for the simplicity,
  but they don't need to be exactly the same - KE server uses semantic reasoning to match patterns in the system.
  For example to get value from temperature sensor '<temperature-sensor-1>' we can use graph:

```text
     ?sensor rdf:type saref:Sensor . 
     ?measurement saref:measurementMadeBy ?sensor .
     ?measurement saref:isMeasuredIn saref:TemperatureUnit .
     ?measurement saref:hasValue ?value .
```  

and graph:

```text
?measurement saref:measurementMadeBy <temperature-sensor-1> . 
?measurement saref:hasValue ?value .
```

In order to add measurement unit to the graph result binding set (assuming such information is shared by the graph
sensor)
we can add following line to the graph:

```text 
?measurement saref:isMeasuredIn ?measurementUnit .
```

The result binding set for the KI graph:

```text
?measurement saref:measurementMadeBy <temperature-sensor-1> . 
?measurement saref:hasValue ?value .
?measurement saref:isMeasuredIn ?measurementUnit .
```

could be:

```json
[
  ...
  {
    "measurementUnit": "om:CelsiusTemperatureUnit",
    "value": "\"12\"^^<http://www.w3.org/2001/XMLSchema#integer>",
    "measurement": "<https://test.bluebird.com/schema/posttest/measurement/662>"
  },
  ...
]
```

for graph:

```text
?measurement saref:measurementMadeBy ?sensor . 
?measurement saref:hasValue ?value .
```

could be:

```json
[
  ...
  {
    "sensor": "<temperature-sensor-1>",
    "value": "\"12\"^^<http://www.w3.org/2001/XMLSchema#integer>",
    "measurement": "<https://test.bluebird.com/schema/posttest/measurement/662>"
  },
  ...
]
```

Unit ontology prefix:

```
om:http://www.ontology-of-units-of-measure.org/resource/om-2/CelsiusTemperatureUnit
```

## Python client

#### Init

``` 
ke_client = KEClient.build()
```

#### Decorating KI methods

For KI requests  (POST - publish information ,ASK - request information)

```
@ke_client.post("graph_name")
def request_method(custom_arg,...):
  ...
  return [{"arg":"binding"}] #  POST binding set must fill all graph variables  (e.g. '?sensor') with some value (it's possible to use graphs without any variables)
```

And to start KI, call:

```
data_bindings = request_method(custom_arg='', ...):
```

For KI responses  (REACT - subscribe to POST,ANSWER)

```
@ke_client.react("graph_name")
def methods(ki_id:str, bindings:List[Dict[str,Any]]):
  ...
  return [{"arg":"binding"}] # can be empty
```

KI response methods are called by the client when appropriate POST/ASK arrives

#### Register

```
ke_client.register()
```

After running 'register()' method on the client it's recommended to execute some sleep for 10-15 seconds to let the KE
update its status  (it's some issue with KE server, it's already included in the sample project) -
otherwise the Knowledge Interactions might behave as they weren't registered despite the fact they were.

## Example

### Import project [from](./example/test_ke_client)

### Run Knowledge engine docker

```
 docker run --rm -p 8280:8280 ghcr.io/tno/knowledge-engine/smart-connector:1.4.0
```

or connect to the existing:

```
KE_REST_ENDPOINT=https://{user}:{pass}@ke-test-bluebird.apps.bst2.paas.psnc.pl/ke-test-runtime/rest/
```

### Run sample clients

Import project from : ``` ./example/test_ke_client```, run clients:

Publishing client:

```commandline
python publish_test.py
```

Consuming client:

```commandline
python subscribe_test.py
```

## REST API docs



 