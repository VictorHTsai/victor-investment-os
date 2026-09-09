import json
from pathlib import Path

import jsonschema

from victor_investment_os.example import run_slv_example


CONTRACTS = Path(__file__).parents[1] / "contracts" / "v1"


def load(name):
    return json.loads((CONTRACTS / name).read_text())


def test_all_json_schemas_are_valid():
    for path in CONTRACTS.glob("*.schema.json"):
        jsonschema.Draft202012Validator.check_schema(json.loads(path.read_text()))


def test_mock_assessment_validates_against_agent_contract():
    result = run_slv_example()
    jsonschema.validate(result["assessment"], load("investment_agent.schema.json"))
    jsonschema.validate(result, load("orchestrator.schema.json"))

