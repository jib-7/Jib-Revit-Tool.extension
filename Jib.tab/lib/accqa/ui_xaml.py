# -*- coding: utf-8 -*-
"""XAML definitions for every window (pure strings - no .NET imports, ASCII only).

Windows are created with XamlReader.Parse(), so no x:Class / code-behind is needed and
the same code works on pyRevit's IronPython and CPython engines. Every element that has
an x:Name is exposed to Python through ui_base.Controls (c.<name>).
"""
import re

_NS = ('xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" '
       'xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"')

_RESOURCES = """
<Window.Resources>
  <Style TargetType="Button">
    <Setter Property="Padding" Value="14,5"/>
    <Setter Property="Margin" Value="6,0,0,0"/>
    <Setter Property="MinWidth" Value="84"/>
  </Style>
  <Style x:Key="Primary" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
    <Setter Property="Background" Value="#1F6FB2"/>
    <Setter Property="Foreground" Value="White"/>
    <Setter Property="BorderBrush" Value="#17588F"/>
  </Style>
  <Style x:Key="Danger" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
    <Setter Property="Foreground" Value="#B00020"/>
  </Style>
  <Style x:Key="Lbl" TargetType="TextBlock">
    <Setter Property="FontWeight" Value="SemiBold"/>
    <Setter Property="Foreground" Value="#33404D"/>
    <Setter Property="Margin" Value="0,0,0,3"/>
  </Style>
  <Style TargetType="TextBox">
    <Setter Property="Padding" Value="4,4"/>
  </Style>
  <Style TargetType="CheckBox">
    <Setter Property="Margin" Value="0,4,0,4"/>
  </Style>
</Window.Resources>
"""


def build(title, width, height, header, sub, body, min_width=None, min_height=None):
    """Wrap a body (one root element) in the standard window with header band."""
    return (
        '<Window %s Title="%s" Width="%d" Height="%d" MinWidth="%d" MinHeight="%d" '
        'WindowStartupLocation="CenterScreen" FontFamily="Segoe UI" FontSize="13" '
        'Background="#F5F7FA" ShowInTaskbar="False">%s'
        '<Grid><Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/></Grid.RowDefinitions>'
        '<Border Grid.Row="0" Background="#12385F" Padding="16,10">'
        '<StackPanel><TextBlock x:Name="HeaderTitle" Text="%s" Foreground="White" FontSize="18" FontWeight="SemiBold"/>'
        '<TextBlock x:Name="HeaderSub" Text="%s" Foreground="#C8D8EA" FontSize="12" TextWrapping="Wrap"/></StackPanel></Border>'
        '<Grid Grid.Row="1" Margin="14">%s</Grid></Grid></Window>'
    ) % (_NS, title, width, height, min_width or width, min_height or height, _RESOURCES, header, sub, body)


def names(xaml):
    """All x:Name values in a XAML string (in document order)."""
    return re.findall(r'x:Name="([A-Za-z0-9_]+)"', xaml)


# ---------------------------------------------------------------------------
# Add / edit folder link
# ---------------------------------------------------------------------------
LINK_DIALOG = build("ACC Quick Access", 520, 640, "Add ACC Link", "", """
<DockPanel>
  <StackPanel DockPanel.Dock="Bottom" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,10,0,0">
    <Button x:Name="btnTest" Content="Test URL"/>
    <Button x:Name="btnSave" Content="Save" IsDefault="True" Style="{StaticResource Primary}"/>
    <Button x:Name="btnCancel" Content="Cancel" IsCancel="True"/>
  </StackPanel>
  <TextBlock x:Name="lblError" DockPanel.Dock="Bottom" Foreground="#B00020" TextWrapping="Wrap" Margin="0,8,0,0" MinHeight="36"/>
  <ScrollViewer VerticalScrollBarVisibility="Auto">
    <StackPanel Margin="0,0,6,0">
      <TextBlock Style="{StaticResource Lbl}" Text="Project Name *"/>
      <ComboBox x:Name="cmbProject" IsEditable="True" Margin="0,0,0,10" Padding="4,4"
                ToolTip="Type a new project name or pick an existing project to add another folder to it"/>
      <TextBlock Style="{StaticResource Lbl}" Text="Project Number"/>
      <TextBox x:Name="txtNumber" Margin="0,0,0,10"/>
      <TextBlock Style="{StaticResource Lbl}" Text="Folder Name *"/>
      <TextBox x:Name="txtFolder" Margin="0,0,0,10"/>
      <TextBlock Style="{StaticResource Lbl}" Text="Folder Category"/>
      <ComboBox x:Name="cmbCategory" Margin="0,0,0,10" Padding="4,4"/>
      <TextBlock Style="{StaticResource Lbl}" Text="ACC URL *"/>
      <TextBox x:Name="txtUrl" TextWrapping="Wrap" AcceptsReturn="False" MinHeight="58"
               VerticalScrollBarVisibility="Auto" Margin="0,0,0,10"
               ToolTip="Paste the full folder address from your browser. It is saved exactly as pasted."/>
      <TextBlock Style="{StaticResource Lbl}" Text="Description (optional)"/>
      <TextBox x:Name="txtDesc" TextWrapping="Wrap" AcceptsReturn="True" Height="60" VerticalScrollBarVisibility="Auto"/>
    </StackPanel>
  </ScrollViewer>
</DockPanel>
""", 520, 600)

# ---------------------------------------------------------------------------
# Edit project details
# ---------------------------------------------------------------------------
PROJECT_DIALOG = build("ACC Quick Access", 500, 520, "Edit Project", "", """
<DockPanel>
  <StackPanel DockPanel.Dock="Bottom" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,10,0,0">
    <Button x:Name="btnSave" Content="Save" IsDefault="True" Style="{StaticResource Primary}"/>
    <Button x:Name="btnCancel" Content="Cancel" IsCancel="True"/>
  </StackPanel>
  <TextBlock x:Name="lblError" DockPanel.Dock="Bottom" Foreground="#B00020" TextWrapping="Wrap" Margin="0,8,0,0" MinHeight="36"/>
  <StackPanel>
    <TextBlock Style="{StaticResource Lbl}" Text="Project Name *"/>
    <TextBox x:Name="txtName" Margin="0,0,0,10"/>
    <TextBlock Style="{StaticResource Lbl}" Text="Project Number"/>
    <TextBox x:Name="txtNumber" Margin="0,0,0,10"/>
    <TextBlock Style="{StaticResource Lbl}" Text="Cloud project GUID (optional - helps automatic detection)"/>
    <TextBox x:Name="txtGuid" Margin="0,0,0,10"/>
    <TextBlock Style="{StaticResource Lbl}" Text="Revit models remembered for this project"/>
    <ListBox x:Name="lstModels" Height="110"/>
    <Button x:Name="btnRemoveModel" Content="Remove selected model" HorizontalAlignment="Left" Margin="0,6,0,0"/>
  </StackPanel>
</DockPanel>
""", 500, 520)

# ---------------------------------------------------------------------------
# All Projects (tree)
# ---------------------------------------------------------------------------
PROJECTS_WINDOW = build("ACC Quick Access - All Projects", 800, 640, "All Projects",
                        "Double-click a folder to open it in your browser", """
<Grid>
  <Grid.RowDefinitions>
    <RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/>
  </Grid.RowDefinitions>
  <DockPanel Grid.Row="0" Margin="0,0,0,8">
    <Button x:Name="btnClearSearch" Content="Clear" DockPanel.Dock="Right" MinWidth="60"/>
    <TextBlock Text="Search:" DockPanel.Dock="Left" VerticalAlignment="Center" Margin="0,0,8,0"/>
    <TextBox x:Name="txtSearch" ToolTip="Search by project name, project number or folder name"/>
  </DockPanel>
  <TreeView x:Name="tree" Grid.Row="1" BorderBrush="#C9D3DF"/>
  <TextBlock x:Name="lblStatus" Grid.Row="2" Foreground="#667788" Margin="0,6,0,0"/>
  <DockPanel Grid.Row="3" Margin="0,8,0,0">
    <Button x:Name="btnClose" Content="Close" DockPanel.Dock="Right" IsCancel="True"/>
    <WrapPanel>
      <Button x:Name="btnOpen" Content="Open Folder" Style="{StaticResource Primary}" Margin="0,0,0,4"/>
      <Button x:Name="btnAddProject" Content="Add Project" Margin="6,0,0,4"/>
      <Button x:Name="btnAddFolder" Content="Add Folder" Margin="6,0,0,4"/>
      <Button x:Name="btnEdit" Content="Edit" Margin="6,0,0,4"/>
      <Button x:Name="btnDelete" Content="Delete" Style="{StaticResource Danger}" Margin="6,0,0,4"/>
      <Button x:Name="btnExpand" Content="Expand All" Margin="6,0,0,4"/>
      <Button x:Name="btnCollapse" Content="Collapse All" Margin="6,0,0,4"/>
    </WrapPanel>
  </DockPanel>
</Grid>
""", 640, 480)

# ---------------------------------------------------------------------------
# Manage Links
# ---------------------------------------------------------------------------
MANAGE_WINDOW = build("ACC Quick Access - Manage Links", 900, 620, "Manage Links",
                      "Add, edit, rename, re-categorise, test and delete saved projects and folders", """
<Grid>
  <Grid.ColumnDefinitions><ColumnDefinition Width="290"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
  <Grid.RowDefinitions><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
  <DockPanel Grid.Column="0" Grid.Row="0" Margin="0,0,10,0">
    <TextBlock Text="Projects" Style="{StaticResource Lbl}" DockPanel.Dock="Top"/>
    <TextBox x:Name="txtSearch" DockPanel.Dock="Top" Margin="0,0,0,6" ToolTip="Search projects by name or number"/>
    <Button x:Name="btnAddProject" Content="Add Project / Link..." DockPanel.Dock="Bottom" Margin="0,8,0,0"/>
    <ListBox x:Name="lstProjects" BorderBrush="#C9D3DF"/>
  </DockPanel>
  <DockPanel Grid.Column="1" Grid.Row="0">
    <StackPanel DockPanel.Dock="Top" Margin="0,0,0,8">
      <TextBlock x:Name="lblProjName" FontSize="16" FontWeight="SemiBold" Text="Select a project"/>
      <TextBlock x:Name="lblProjInfo" Foreground="#667788" TextWrapping="Wrap" Margin="0,2,0,6"/>
      <StackPanel Orientation="Horizontal">
        <Button x:Name="btnEditProject" Content="Edit Project..." Margin="0,0,0,0"/>
        <Button x:Name="btnDeleteProject" Content="Delete Project" Style="{StaticResource Danger}"/>
      </StackPanel>
    </StackPanel>
    <WrapPanel DockPanel.Dock="Bottom" Margin="0,8,0,0">
      <Button x:Name="btnAddFolder" Content="Add Folder..." Margin="0,0,0,4"/>
      <Button x:Name="btnEditFolder" Content="Edit Folder..." Margin="6,0,0,4"/>
      <Button x:Name="btnTestUrl" Content="Test URL" Margin="6,0,0,4"/>
      <Button x:Name="btnOpen" Content="Open" Margin="6,0,0,4"/>
      <Button x:Name="btnDeleteFolder" Content="Delete Folder" Style="{StaticResource Danger}" Margin="6,0,0,4"/>
    </WrapPanel>
    <TextBlock Text="Folders" Style="{StaticResource Lbl}" DockPanel.Dock="Top"/>
    <ListBox x:Name="lstFolders" BorderBrush="#C9D3DF"/>
  </DockPanel>
  <Button x:Name="btnClose" Content="Close" Grid.Row="1" Grid.Column="1" HorizontalAlignment="Right" Margin="0,10,0,0" IsCancel="True"/>
</Grid>
""", 760, 480)

# ---------------------------------------------------------------------------
# Current Project
# ---------------------------------------------------------------------------
CURRENT_WINDOW = build("ACC Quick Access - Current Project", 640, 640, "Current Project", "", """
<Grid>
  <Grid.RowDefinitions>
    <RowDefinition Height="Auto"/><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/>
  </Grid.RowDefinitions>
  <Border Grid.Row="0" Background="White" BorderBrush="#C9D3DF" BorderThickness="1" Padding="12" Margin="0,0,0,8">
    <StackPanel>
      <TextBlock x:Name="lblModel" Foreground="#667788" TextWrapping="Wrap"/>
      <TextBlock x:Name="lblProject" FontSize="17" FontWeight="SemiBold" Margin="0,4,0,0" TextWrapping="Wrap"/>
      <TextBlock x:Name="lblMatch" Foreground="#667788" Margin="0,2,0,0" TextWrapping="Wrap"/>
      <TextBlock x:Name="lblMessage" Foreground="#B25E00" Margin="0,6,0,0" TextWrapping="Wrap"/>
    </StackPanel>
  </Border>
  <Expander Grid.Row="1" Header="Detection details" Margin="0,0,0,8">
    <TextBox x:Name="txtDiag" IsReadOnly="True" Height="130" TextWrapping="NoWrap" FontFamily="Consolas" FontSize="11"
             VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Auto" Margin="0,6,0,0"/>
  </Expander>
  <ListBox x:Name="lstFolders" Grid.Row="2" BorderBrush="#C9D3DF"/>
  <DockPanel Grid.Row="3" Margin="0,10,0,0">
    <Button x:Name="btnClose" Content="Close" DockPanel.Dock="Right" IsCancel="True"/>
    <WrapPanel>
      <Button x:Name="btnOpen" Content="Open Folder" Style="{StaticResource Primary}" Margin="0,0,0,4"/>
      <Button x:Name="btnAddFolder" Content="Add Folder..." Margin="6,0,0,4"/>
      <Button x:Name="btnRegister" Content="Add Project..." Margin="6,0,0,4"/>
      <Button x:Name="btnChange" Content="Select Project..." Margin="6,0,0,4"/>
    </WrapPanel>
  </DockPanel>
</Grid>
""", 560, 520)

# ---------------------------------------------------------------------------
# Recent Projects
# ---------------------------------------------------------------------------
RECENT_WINDOW = build("ACC Quick Access - Recent Projects", 820, 520, "Recent Projects",
                      "Saved project links you opened most recently (not recently opened Revit models)", """
<Grid>
  <Grid.ColumnDefinitions><ColumnDefinition Width="320"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
  <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
  <TextBlock Text="Projects (newest first)" Style="{StaticResource Lbl}" Grid.Row="0" Grid.Column="0"/>
  <TextBlock Text="Folders (double-click to open)" Style="{StaticResource Lbl}" Grid.Row="0" Grid.Column="1" Margin="10,0,0,3"/>
  <ListBox x:Name="lstRecent" Grid.Row="1" Grid.Column="0" BorderBrush="#C9D3DF"/>
  <ListBox x:Name="lstFolders" Grid.Row="1" Grid.Column="1" BorderBrush="#C9D3DF" Margin="10,0,0,0"/>
  <DockPanel Grid.Row="2" Grid.ColumnSpan="2" Margin="0,10,0,0">
    <Button x:Name="btnClose" Content="Close" DockPanel.Dock="Right" IsCancel="True"/>
    <TextBlock x:Name="lblNote" Foreground="#B25E00" DockPanel.Dock="Right" VerticalAlignment="Center" Margin="8,0,8,0"/>
    <WrapPanel>
      <Button x:Name="btnOpen" Content="Open Folder" Style="{StaticResource Primary}" Margin="0"/>
      <Button x:Name="btnClear" Content="Clear History" Style="{StaticResource Danger}"/>
    </WrapPanel>
  </DockPanel>
</Grid>
""", 700, 400)

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
SETTINGS_WINDOW = build("ACC Quick Access - Settings", 560, 560, "Settings", "", """
<DockPanel>
  <DockPanel DockPanel.Dock="Bottom" Margin="0,10,0,0">
    <StackPanel Orientation="Horizontal" DockPanel.Dock="Right">
      <Button x:Name="btnSave" Content="Save" IsDefault="True" Style="{StaticResource Primary}"/>
      <Button x:Name="btnCancel" Content="Cancel" IsCancel="True"/>
    </StackPanel>
    <WrapPanel>
      <Button x:Name="btnResetSettings" Content="Reset Settings" Margin="0"/>
      <Button x:Name="btnDeleteAll" Content="Delete All Saved Data..." Style="{StaticResource Danger}"/>
    </WrapPanel>
  </DockPanel>
  <StackPanel>
    <CheckBox x:Name="chkAutoDetect" Content="Enable automatic current project detection"/>
    <CheckBox x:Name="chkRecent" Content="Enable recent project tracking"/>
    <DockPanel Margin="0,4,0,4">
      <TextBlock Text="Maximum recent projects (1-10):" VerticalAlignment="Center" Margin="0,0,8,0"/>
      <ComboBox x:Name="cmbMaxRecent" Width="70" HorizontalAlignment="Left"/>
    </DockPanel>
    <CheckBox x:Name="chkBrowser" Content="Open links in the default browser (if off, the URL is copied to the clipboard)"/>
    <CheckBox x:Name="chkConfirm" Content="Show confirmation before deleting a folder (deleting a project always asks)"/>
    <TextBlock Text="Configuration file" Style="{StaticResource Lbl}" Margin="0,14,0,3"/>
    <TextBox x:Name="txtConfigPath" IsReadOnly="True"/>
    <TextBlock Text="Log file" Style="{StaticResource Lbl}" Margin="0,10,0,3"/>
    <TextBox x:Name="txtLogPath" IsReadOnly="True"/>
    <WrapPanel Margin="0,8,0,0">
      <Button x:Name="btnOpenFolder" Content="Open Data Folder" Margin="0"/>
      <Button x:Name="btnCopyPath" Content="Copy Config Path"/>
    </WrapPanel>
    <TextBlock x:Name="lblInfo" Foreground="#667788" TextWrapping="Wrap" Margin="0,12,0,0"/>
  </StackPanel>
</DockPanel>
""", 520, 520)

# ---------------------------------------------------------------------------
# Backup / Restore
# ---------------------------------------------------------------------------
BACKUP_WINDOW = build("ACC Quick Access - Backup / Restore", 560, 360, "Backup / Restore",
                      "Export your saved links to a file, or import a previous export", """
<DockPanel>
  <Button x:Name="btnClose" Content="Close" DockPanel.Dock="Bottom" HorizontalAlignment="Right" Margin="0,10,0,0" IsCancel="True"/>
  <StackPanel>
    <TextBlock x:Name="lblSummary" FontSize="14" Margin="0,0,0,12" TextWrapping="Wrap"/>
    <Button x:Name="btnExport" Content="Export Backup..." Margin="0,0,0,8" HorizontalAlignment="Left" MinWidth="190"/>
    <Button x:Name="btnImport" Content="Import / Restore Backup..." Margin="0,0,0,8" HorizontalAlignment="Left" MinWidth="190"/>
    <TextBlock x:Name="lblStatus" Foreground="#2E7D32" TextWrapping="Wrap" Margin="0,10,0,0"/>
  </StackPanel>
</DockPanel>
""", 520, 320)

IMPORT_PREVIEW = build("ACC Quick Access - Import Preview", 640, 600, "Import Preview",
                       "Review what will happen before anything is changed", """
<DockPanel>
  <StackPanel DockPanel.Dock="Bottom" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,10,0,0">
    <Button x:Name="btnImport" Content="Import" Style="{StaticResource Primary}"/>
    <Button x:Name="btnCancel" Content="Cancel" IsCancel="True"/>
  </StackPanel>
  <StackPanel DockPanel.Dock="Bottom" Margin="0,10,0,0">
    <RadioButton x:Name="rbMerge" Content="Merge - keep my current data and add the backup (duplicates are skipped)" IsChecked="True" Margin="0,2"/>
    <RadioButton x:Name="rbReplace" Content="Replace - discard my current projects and use the backup contents" Margin="0,2"/>
    <CheckBox x:Name="chkSettings" Content="Also import the settings stored in the backup" Margin="0,8,0,0"/>
  </StackPanel>
  <TextBox x:Name="txtPreview" IsReadOnly="True" FontFamily="Consolas" FontSize="12" TextWrapping="NoWrap"
           VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Auto"/>
</DockPanel>
""", 560, 480)

# ---------------------------------------------------------------------------
# Generic picker (projects or folders)
# ---------------------------------------------------------------------------
PICKER_WINDOW = build("ACC Quick Access", 520, 520, "Select", "", """
<DockPanel>
  <StackPanel DockPanel.Dock="Bottom" Margin="0,10,0,0">
    <CheckBox x:Name="chkRemember" Content="Remember this Revit model for the selected project" Margin="0,0,0,8"/>
    <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
      <Button x:Name="btnOK" Content="OK" IsDefault="True" Style="{StaticResource Primary}"/>
      <Button x:Name="btnCancel" Content="Cancel" IsCancel="True"/>
    </StackPanel>
  </StackPanel>
  <TextBlock x:Name="lblPrompt" DockPanel.Dock="Top" TextWrapping="Wrap" Margin="0,0,0,8"/>
  <TextBox x:Name="txtSearch" DockPanel.Dock="Top" Margin="0,0,0,6" ToolTip="Type to filter the list"/>
  <ListBox x:Name="lstItems" BorderBrush="#C9D3DF"/>
</DockPanel>
""", 440, 400)
