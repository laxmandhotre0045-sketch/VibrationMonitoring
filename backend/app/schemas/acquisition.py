from typing import Any, List, Optional
from pydantic import BaseModel, Field


class AcquisitionFormulaOut(BaseModel):
    frequencyResolutionHz: float
    blockTimeSeconds: float
    sampleRateHz: float
    requiredSamples: float
    overlapDecimal: float
    totalAcquisitionTimeSeconds: float
    averageCount: float
    fmaxHz: float
    lor: float
    stepSizeSamples: float


class AcquisitionChannelOut(BaseModel):
    transducerType: str
    signalType: str
    channelIndex: int
    machineAxis: str


class EdgeAcquisitionConfigOut(BaseModel):
    acquisitionFormula: AcquisitionFormulaOut
    minutes: str
    averaging: int
    sensitivityMvPerG: Optional[float] = None
    totalChannelCount: int
    averageCount: int
    lastAveraging: Optional[Any] = None
    lastOverlapping: Optional[Any] = None
    lor: str
    fmax: str
    windowType: str
    sensorId: str
    channels: List[AcquisitionChannelOut]
    success: bool = True
    overlapping: int
    ksps: str
    id: int = 1
    overlapPercentage: int
    platformSensorId: str = Field(description="Internal UUID — use for upload API until device_id upload is added")
