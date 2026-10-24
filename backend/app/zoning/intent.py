"""What the user wants to build, as a fixed set of fields.

The intent is the only input a person types. In phase 1 it arrives as a form.
Later a small model call may fill the same fields from free text. Either way the
rest of the pipeline sees only these fields. A field the user does not give stays
None, and every downstream step treats None as "unknown", never as zero.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Mode = Literal["buyer", "professional"]
Project = Literal[
    "addition",  # keep the house, add to it (rear, side or up)
    "new_build",  # demolish and rebuild
    "convert",  # more units inside the existing envelope
    "garden_suite",
    "laneway_suite",
    "sever",  # divide the lot
    "unknown",
]


class Intent(BaseModel):
    mode: Mode = "buyer"
    project: Project = "unknown"
    text: str | None = Field(None, description="The user's own words, kept for the record")

    keep_existing_walls: bool | None = Field(
        None, description="True when the plan keeps the existing main walls (alteration, not demolition)"
    )
    sever_lot: bool | None = None

    proposed_units: int | None = Field(None, ge=1)
    proposed_storeys: int | None = Field(None, ge=1)
    proposed_height_m: float | None = Field(None, gt=0)
    proposed_gfa_m2: float | None = Field(None, gt=0, description="Gross floor area as the by-law counts it")
    proposed_footprint_m2: float | None = Field(None, gt=0, description="Ground area of all buildings after the work")
    proposed_building_depth_m: float | None = Field(None, gt=0)
    proposed_building_length_m: float | None = Field(None, gt=0)
    proposed_front_setback_m: float | None = Field(None, ge=0)
    proposed_side_setback_m: float | None = Field(None, ge=0, description="The smaller of the 2 side yards")
    proposed_rear_setback_m: float | None = Field(None, ge=0)

    @model_validator(mode="after")
    def _infer_project(self) -> "Intent":
        if self.project == "unknown":
            if self.sever_lot:
                self.project = "sever"
            elif self.keep_existing_walls is True:
                self.project = "addition"
            elif self.keep_existing_walls is False:
                self.project = "new_build"
        if self.project == "sever" and self.sever_lot is None:
            self.sever_lot = True
        if self.project == "new_build" and self.keep_existing_walls is None:
            self.keep_existing_walls = False
        if self.project == "addition" and self.keep_existing_walls is None:
            self.keep_existing_walls = True
        return self
