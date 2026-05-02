from fastapi import APIRouter, HTTPException, Request, status

from ..alarm_engine import alarm_engine
from ..models import Alarm, AlarmsResponse


router = APIRouter()


@router.get("/alarms", response_model=AlarmsResponse)
async def alarms() -> AlarmsResponse:
    return await alarm_engine.evaluate_and_list()


@router.post("/alarms/{id}/ack", response_model=Alarm)
async def acknowledge_alarm(id: str, request: Request) -> Alarm:
    actor = request.headers.get("x-operator", "operator")
    alarm = await alarm_engine.acknowledge(id, actor=actor)
    if alarm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Alarm '{id}' not found")
    return alarm


@router.post("/alarms/{id}/unack", response_model=Alarm)
async def unacknowledge_alarm(id: str, request: Request) -> Alarm:
    actor = request.headers.get("x-operator", "operator")
    alarm = await alarm_engine.unacknowledge(id, actor=actor)
    if alarm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Alarm '{id}' not found")
    return alarm
