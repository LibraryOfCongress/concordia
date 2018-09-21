from openpyxl import load_workbook


def slurp_excel(filename):
    """
    Return a list containing dictionaries for each row of the provided spreadsheet

    This assumes that the first row of every worksheet contains the headers
    """
    wb = load_workbook(filename=filename)

    cells = []

    for worksheet in wb.worksheets:
        rows = worksheet.rows
        headers = [clean_cell_value(i) for i in next(rows)]

        for row in rows:
            values = []
            for cell in row:
                values.append(clean_cell_value(cell))

            cells.append(dict(zip(headers, values)))

    return cells


def clean_cell_value(cell):
    if cell.data_type in ("s",):
        return cell.value.strip()
    else:
        return cell.value
