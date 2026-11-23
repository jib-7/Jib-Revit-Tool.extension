# Troubleshooting

**The tab does not appear.** Check the folder is directly inside a pyRevit extensions directory and is named
`ACCQuickAccess.extension` (not nested twice after unzipping). pyRevit tab > Reload. pyRevit tab > Settings >
*Custom Extension Directories* must list the parent folder if you did not use the default location.
Check the pyRevit Output/log for a script-parsing error.

**"ImportError: No module named accqa".** The `lib` folder must sit next to `ACC Quick Access.tab`
inside the extension. Reload pyRevit after copying.

**A window shows "Something went wrong ...".** Open `%APPDATA%\pyRevit\ACCQuickAccess\logs\accqa.log`
(Settings > *Open Data Folder*). Send the last traceback when asking for help.

**Current Project says "not identified".** Expand *Detection details*: it lists the GUIDs/paths Revit returned
and notes such as "ModelPath.GetProjectGUID() is not available". Fix: click *Select Project...* and tick
*Remember this Revit model*. Or paste the cloud project GUID in Manage Links > Edit Project.
Non-cloud (local/server) models can only match by remembered title or a project number in the title.

**More than one project matches.** Two projects share a remembered model title or GUID. Choose manually and
remove the wrong remembered model in Edit Project.

**Browser opens but ACC shows an error / login page.** Normal: Autodesk controls sign-in and permissions.
The folder may have been moved or deleted in ACC, or you lack access. Re-copy the URL from ACC and edit the
folder in Manage Links.

**Nothing opens, I get "could not be opened".** The message lists which launch methods failed
(Process.Start / os.startfile / webbrowser). Check a default browser is set in Windows. As a workaround switch off
*Open links in the default browser* in Settings to copy URLs to the clipboard.

**Config problems.** If `config.json` is damaged you get a notice; the damaged file is kept as
`config.corrupt-<time>.json` and the last `.bak` is restored. You can also restore any file in `backups\`
through Backup / Restore > Import.

**Dialogs appear behind Revit.** Windows are owned by the Revit main window; if you use multiple monitors
with remote desktop the owner handle can fail - this is logged and the dialog is still shown.

**Icons look blurry.** pyRevit scales the 96x96 PNGs; set Windows display scaling to 100-150 % for best results.

**A button shows only an empty pyRevit output window (v1.0.1+).** Each button now writes to
`%APPDATA%\pyRevit\ACCQuickAccess\logs\startup.log` ("START ..." then "END ..." or "FAILED ..." with the traceback) and prints
errors into the pyRevit output window. Send that file when reporting a problem.
