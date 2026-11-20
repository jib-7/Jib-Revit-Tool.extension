# -*- coding: utf-8 -*-
__title__ = "Assign\nMaterial Data"
__doc__ = ("Reads MATERIAL_SCHEDULE.xlsx and writes the schedule values into "
           "parameters of Revit elements whose family Type Name contains the CODE column (type or instance parameters).")

import re
import zipfile
import xml.etree.ElementTree as ET
from System.Collections.Generic import List
from pyrevit import revit, DB, forms, script

try:
    text_type = unicode          # IronPython 2.7
except NameError:
    text_type = str              # IronPython 3 / CPython

doc = revit.doc
output = script.get_output()

# =====================  SETTINGS - EDIT HERE  =====================
CODE_HEADER = "CODE"          # Excel column that holds the code
# The code is matched against the family TYPE NAME (and also the Type Mark, if filled).
MATCH_PARAM = "Type Mark"

# Excel header  ->  Revit parameter name (parameters must already exist)
PARAM_MAP = [
    ("MATERIAL CODE",  "Material Name"),
    ("FINISH CODE",    "Material Finish"),
    ("COLOUR CODE",    "Material Color"),
    ("DESCRIPTION 1",  "Material Description 1"),
    ("DESCRIPTION 2",  "Material Description 2"),
    ("CODE",  "Type Mark"),
    ("APPLICATION",    "Description"),
]

# Codes with several rows (e.g. ST1 = top tread / tread / riser):
# these columns are joined with " | ", all others take the first row.
JOIN_COLS = ["APPLICATION", "DESCRIPTION 1", "DESCRIPTION 2"]

# "contains" = the Type Name only has to CONTAIN the Excel code
#              (BEP naming, e.g. "IF1 - Paver", "BBQ-CD1B"). Longest code wins.
# "exact"    = Type Name must equal the code (dashes/spaces/case ignored)
MATCH_MODE = "contains"

# None = scan ALL categories. Or give a list, e.g. ["OST_Floors", "OST_Walls"]
CATEGORY_NAMES = None
# ==================================================================


def norm(v):
    """Excel cell -> clean string (collapsed spaces, no trailing blanks)."""
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return " ".join(text_type(v).split())


NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def col_index(ref):
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return n


def read_xlsx(path):
    """Return {(row, col): value} for the first sheet. Pure Python, no Excel."""
    z = zipfile.ZipFile(path)
    try:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
        # locate first worksheet
        sheet_path = "xl/worksheets/sheet1.xml"
        try:
            wbx = ET.fromstring(z.read("xl/workbook.xml"))
            rid = wbx.find(NS + "sheets").findall(NS + "sheet")[0].get(RNS + "id")
            rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
            for rel in rels:
                if rel.get("Id") == rid:
                    tgt = rel.get("Target").lstrip("/")
                    sheet_path = tgt if tgt.startswith("xl/") else "xl/" + tgt
        except Exception:
            pass
        sheet = ET.fromstring(z.read(sheet_path))
        cells = {}
        for c in sheet.iter(NS + "c"):
            ref = c.get("r")
            t = c.get("t")
            v = c.find(NS + "v")
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(NS + "t"))
            elif v is not None:
                val = v.text
            else:
                continue
            row = int("".join(ch for ch in ref if ch.isdigit()))
            cells[(row, col_index(ref))] = val
        return cells
    finally:
        z.close()


class Grid(object):
    def __init__(self, cells):
        self.cells = cells
        self.n_rows = max(k[0] for k in cells) if cells else 0
        self.n_cols = max(k[1] for k in cells) if cells else 0

    def __getitem__(self, rc):
        return self.cells.get(rc)


# ---------- 1. Read Excel ----------
path = forms.pick_file(file_ext="xlsx")
if not path:
    script.exit()

data = Grid(read_xlsx(path))
n_rows, n_cols = data.n_rows, data.n_cols

# find header row (the row that contains CODE_HEADER)
header_row = None
for r in range(1, min(n_rows, 20) + 1):
    cells = [norm(data[r, c]).upper() for c in range(1, n_cols + 1)]
    if CODE_HEADER in cells:
        header_row = r
        break
if header_row is None:
    forms.alert("Could not find a '{}' header in the first 20 rows.".format(CODE_HEADER),
                exitscript=True)

col_of = {}
for c in range(1, n_cols + 1):
    h = norm(data[header_row, c]).upper()
    if h and h not in col_of:          # first occurrence wins
        col_of[h] = c

code_col = col_of[CODE_HEADER]
needed = [h for h, _ in PARAM_MAP]
missing_cols = [h for h in needed if h not in col_of]
if missing_cols:
    forms.alert("Excel columns not found:\n" + "\n".join(missing_cols), exitscript=True)

# build {code: {header: value}}; blank-code rows continue the previous code
rows_by_code, order = {}, []
current = None
for r in range(header_row + 1, n_rows + 1):
    code = norm(data[r, code_col])
    if code:
        current = code
        if code not in rows_by_code:
            rows_by_code[code] = []
            order.append(code)
    elif current is None:
        continue
    else:
        # continuation row only if it carries data (skips section titles)
        if not any(norm(data[r, col_of[h]]) for h in JOIN_COLS if h in col_of):
            continue
    if current:
        rows_by_code[current].append(
            dict((h, norm(data[r, col_of[h]])) for h in needed))

lookup = {}
for code, rows in rows_by_code.items():
    vals = {}
    for h in needed:
        if h in JOIN_COLS:
            parts = []
            for row in rows:
                if row[h] and row[h] not in parts:
                    parts.append(row[h])
            vals[h] = " | ".join(parts)
        else:
            vals[h] = rows[0][h]
    lookup[code.upper()] = vals

# ---------- 2. Collect Revit element types ----------
def key_of(v):
    """Compare codes ignoring case, spaces, dashes and other symbols."""
    return re.sub(r"[^A-Z0-9]", "", norm(v).upper())


lookup = dict((key_of(k), v) for k, v in lookup.items())

types_col = DB.FilteredElementCollector(doc)
if CATEGORY_NAMES:
    cat_ids = List[DB.ElementId]()
    for n in CATEGORY_NAMES:
        bic = getattr(DB.BuiltInCategory, n, None)
        if bic is not None:
            cat_ids.Add(DB.ElementId(bic))
    types_col = types_col.WherePasses(DB.ElementMulticategoryFilter(cat_ids))
types = list(types_col.WhereElementIsElementType().ToElements())

_inst_cache = {}


def instances_of(type_id):
    """Instances grouped by type id (built once, only if needed)."""
    if not _inst_cache:
        _inst_cache["built"] = True
        for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType():
            tid = e.GetTypeId()
            if tid is not None and tid != DB.ElementId.InvalidElementId:
                _inst_cache.setdefault(tid, []).append(e)
    return _inst_cache.get(type_id, [])


def type_mark(t):
    p = t.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_MARK)
    if p is None:
        p = t.LookupParameter(MATCH_PARAM)
    return (p.AsString() or "") if p else ""


def type_name(t):
    try:
        return DB.Element.Name.GetValue(t) or ""
    except Exception:
        pass
    try:
        return t.Name or ""
    except Exception:
        return ""


# ---------- 3. Match and write ----------
ambiguous = []          # (type name, [codes found inside it])


def find_key(name, mark):
    k = key_of(name)
    if k in lookup:                              # exact match always wins
        return k
    if MATCH_MODE == "contains":
        words = re.sub(r"[^A-Z0-9]+", " ", name.upper())
        hits = [c for c in lookup if c in words]
        if hits:
            hits.sort(key=lambda c: (-len(c), c))   # longest code first
            if len(hits) > 1:
                ambiguous.append((name, hits))
            return hits[0]
    k = key_of(mark)
    if k in lookup:
        return k
    return None


def cat_name(t):
    try:
        return t.Category.Name if t.Category else "-"
    except Exception:
        return "-"


matched_keys = set()
all_names = []          # (type name, category)
missing_params = {}     # param name -> ["Type (Category)", ...]
skipped_params = {}     # param name -> count (read-only / not Text)
n_types_updated = 0
n_inst_updated = 0


def write(p, value, name):
    if p.IsReadOnly or p.StorageType != DB.StorageType.String:
        skipped_params[name] = skipped_params.get(name, 0) + 1
        return False
    p.Set(value)
    return True


with revit.Transaction("Assign material data from Excel"):
    for t in types:
        tn = type_name(t)
        tm = type_mark(t)
        all_names.append((tn, cat_name(t)))
        key = find_key(tn, tm)
        if key is None:
            continue
        matched_keys.add(key)
        vals = lookup[key]
        type_done = False
        for xl_h, rvt_p in PARAM_MAP:
            value = vals[xl_h]
            p = t.LookupParameter(rvt_p)
            if p is not None:                       # type parameter
                if write(p, value, rvt_p):
                    type_done = True
                continue
            found = False                           # instance parameter
            for inst in instances_of(t.Id):
                ip = inst.LookupParameter(rvt_p)
                if ip is not None:
                    found = True
                    if write(ip, value, rvt_p):
                        n_inst_updated += 1
            if not found:
                missing_params.setdefault(rvt_p, []).append(
                    "{} ({})".format(tn, cat_name(t)))
        if type_done:
            n_types_updated += 1

# ---------- 4. Report ----------
output.print_md("## Material data assignment  (mode: {})".format(MATCH_MODE))
output.print_md("**Types scanned:** {}".format(len(types)))
output.print_md("**Codes in Excel:** {}  |  **matched in model:** {}".format(
    len(order), len(matched_keys)))
output.print_md("**Types updated:** {}  |  **instance parameter writes:** {}".format(
    n_types_updated, n_inst_updated))

if ambiguous:
    output.print_md("### Type names containing more than one code (longest code was used)")
    seen = set()
    for n, hits in ambiguous:
        if n not in seen:
            seen.add(n)
            output.print_md("- {} -> {}".format(n, ", ".join(hits)))

unmatched = [c for c in order if key_of(c) not in matched_keys]
if unmatched:
    output.print_md("### Excel codes with no matching Type Name in the model")
    output.print_md(", ".join(unmatched))
    output.print_md("### Model types whose name contains the unmatched code (candidates)")
    name_keys = [(key_of(n), n, c) for n, c in all_names if n]
    for code in unmatched:
        ck = key_of(code)
        cands = sorted(set("{} ({})".format(n, c) for k, n, c in name_keys if ck in k))
        if cands:
            output.print_md("- **{}** -> {}".format(code, "; ".join(cands[:6])))
        else:
            output.print_md("- **{}** -> _no type name contains it_".format(code))
if missing_params:
    output.print_md("### Matched types that do not have the parameter (not bound to that category)")
    for k in sorted(missing_params):
        output.print_md("- `{}`: {}".format(k, "; ".join(sorted(set(missing_params[k]))[:8])))
if skipped_params:
    output.print_md("### Parameters skipped (read-only or not a Text parameter)")
    for k in sorted(skipped_params):
        output.print_md("- `{}` ({}x)".format(k, skipped_params[k]))