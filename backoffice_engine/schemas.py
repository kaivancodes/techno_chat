"""
Data structures for text chunks and sources.
"""
from typing import TypedDict, Optional

class Segment(TypedDict, total=False):
    text: str
    page_index: Optional[int]
    slide_index: Optional[int]
    sheet_name: Optional[str]
    row_start: Optional[int]
    row_end: Optional[int]
    line_start: Optional[int]
    line_end: Optional[int]
    section_name: Optional[str]

class SourceEntry(TypedDict, total=False):
    file_name: str
    file_type: str
    file_id: Optional[int]
    image_url: Optional[str]
    page_index: Optional[int]
    slide_index: Optional[int]
    sheet_name: Optional[str]
    row_start: Optional[int]
    row_end: Optional[int]
    line_start: Optional[int]
    line_end: Optional[int]
    section_name: Optional[str]
