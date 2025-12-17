from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell


def slurp_excel(filename: str) -> list[dict[str, Any]]:
    """
    Parse an Excel workbook into a list of row dictionaries.

    Each worksheet is read in order. The first row of each sheet is treated
    as the header; subsequent rows become dictionaries mapping header names
    to cell values (after basic cleaning via `clean_cell_value`).

    Args:
        filename (str): Path to the XLSX file.

    Returns:
        list[dict[str, Any]]: One dict per non-header row across all sheets.
    """
    wb = load_workbook(filename=filename)

    cells: list[dict[str, Any]] = []

    for worksheet in wb.worksheets:
        rows = worksheet.rows
        headers = [clean_cell_value(i) for i in next(rows)]

        for row in rows:
            values: list[Any] = []
            for cell in row:
                values.append(clean_cell_value(cell))

            cells.append(dict(zip(headers, values, strict=True)))

    return cells


def clean_cell_value(cell: Cell) -> Any:
    """
    Return a normalized Python value for an openpyxl cell.

    If the cell is a string type ('s'), leading/trailing whitespace is stripped;
    otherwise the raw value is returned.

    Args:
        cell (Cell): openpyxl cell to normalize.

    Returns:
        Any: Cleaned value suitable for serialization.
    """
    if cell.data_type in ("s",):
        return cell.value.strip()
    else:
        return cell.value
