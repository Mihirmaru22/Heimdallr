from pydantic import BaseModel

class ReasearchObjective(BaseModel):
    target: str
    target_type: str
    intelligence_goal: str
    required_Fields: list[str]
    success_criteria: str