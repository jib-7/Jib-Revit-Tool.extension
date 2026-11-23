# Compatibility notes (Revit 2024, 2025, 2026)

## Python engines
* Written to run unchanged on pyRevit's IronPython 2.7 (default), IronPython 3.4 and CPython 3.8+:
  no f-strings, `nonlocal`, annotations or keyword-only arguments; all source is ASCII; JSON is read/written as
  bytes with explicit UTF-8; `os.replace` is optional (fallback for IronPython 2.7).
* No external packages are used. WPF windows are created from XAML strings with `XamlReader.Parse`
  and wired in Python (no code-behind, no data binding), which behaves the same on all engines.
* Static checks (AST scan for Python 2.7-incompatible syntax, ASCII-only, XAML well-formedness, control names)
  are part of `tests/run_tests.py`. IronPython itself was **not** available to the author, so runtime behaviour on
  IronPython is unverified.

## Revit versions
* Revit 2024 runs on .NET Framework 4.8; Revit 2025 and 2026 run on .NET 8. WPF, `System.Diagnostics.Process`
  and `Microsoft.Win32` file dialogs exist in both. Because .NET 8 defaults `UseShellExecute` to false, the URL
  launcher sets `UseShellExecute = True` explicitly (this is what makes the default browser open).
* `revit_compat.py` is the single place that touches version-dependent Revit API. Members used, each guarded by
  try/except and reported in the *Detection details* panel when missing:
  `Document.IsModelInCloud`, `Document.GetCloudModelPath()`, `Document.GetWorksharingCentralModelPath()`,
  `ModelPath.CloudPath`, `ModelPath.GetProjectGUID()`, `ModelPath.GetModelGUID()`, `ModelPath.Region`,
  `ModelPathUtils.ConvertModelPathToUserVisiblePath()`, `Document.Title`, `Document.PathName`,
  `Document.IsFamilyDocument`, `Document.IsWorkshared`, `Application.Username`.
  These come from the author's knowledge of the public Revit API; they were **not** verified against Revit 2024-2026
  in this build. If one is missing, detection falls back to the next tier instead of failing.
* The exact text of the user-visible cloud path (assumed `Provider://Project/.../Model.rvt`) is an assumption.
  It is used only for *exact* project-name comparison, so a different format just means "no match" and manual
  selection (with "remember this model") takes over.
* Desktop Connector paths containing an `ACCDocs` folder are also used as a name hint (best effort).
* The folder icon glyph uses the `Segoe MDL2 Assets` font (Windows 10/11; Windows 11 also provides it via Segoe Fluent Icons).

## Not used
No private/undocumented Autodesk APIs, no Forge/APS calls, no stored tokens.

## Revit 2025/2026 (.NET 8) assembly note
On .NET 8 `System.Diagnostics.Process` is its own assembly. v1.0.0/1.0.1 failed on Revit 2026 with
`ImportError: Cannot import name Process` because it was not referenced. Fixed in v1.0.2 (`clr.AddReference`).
