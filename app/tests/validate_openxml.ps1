param([Parameter(Mandatory=$true)][string]$File,[Parameter(Mandatory=$true)][string]$SdkPath)
$ErrorActionPreference='Stop'
Add-Type -Path ([IO.Path]::GetFullPath($SdkPath))
Add-Type -AssemblyName WindowsBase
$doc=[DocumentFormat.OpenXml.Packaging.SpreadsheetDocument]::Open([IO.Path]::GetFullPath($File),$false)
try {
 $validator=New-Object DocumentFormat.OpenXml.Validation.OpenXmlValidator([DocumentFormat.OpenXml.FileFormatVersions]::Office2019)
 $errors=@($validator.Validate($doc))
 foreach($e in $errors){Write-Output ($e.Part.Uri.ToString()+': '+$e.Path.XPath+': '+$e.Description)}
 Write-Output ("Open XML validation errors: "+$errors.Count)
 if($errors.Count){exit 1}
} finally {$doc.Dispose()}
