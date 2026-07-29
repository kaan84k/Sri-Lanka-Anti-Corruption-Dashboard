<#
.SYNOPSIS
    Stage, commit, and push the working tree to GitHub.

.DESCRIPTION
    Manual push helper. Stages everything, commits with the supplied message, and
    pushes to origin. If the current branch has no upstream yet, it is published
    with -u so later pushes need no arguments.

.PARAMETER Message
    Commit message. Required.

.PARAMETER Paths
    Optional list of paths to stage instead of everything.

.PARAMETER DryRun
    Show what would be committed and pushed, then stop.

.EXAMPLE
    .\scripts\push.ps1 "fix: reject lettered sub-codes"

.EXAMPLE
    .\scripts\push.ps1 "docs: update report" -Paths docs, README.md

.EXAMPLE
    .\scripts\push.ps1 "wip" -DryRun
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Message,

    [string[]] $Paths,

    [switch] $DryRun
)

$ErrorActionPreference = 'Stop'

# Run from the repository root regardless of where the caller stands.
$root = git rev-parse --show-toplevel
if (-not $?) { throw "Not inside a git repository." }
Set-Location $root

$branch = git rev-parse --abbrev-ref HEAD
if ($branch -eq 'HEAD') { throw "Detached HEAD - check out a branch before pushing." }
if ($branch -eq 'main')  { throw "Refusing to push straight to main. Create a branch first." }

if ($Paths) { git add -- $Paths } else { git add -A }

$staged = git diff --cached --name-only
if (-not $staged) {
    Write-Host "Nothing staged - working tree is clean. Nothing to push." -ForegroundColor Yellow
    exit 0
}

Write-Host "Branch:  $branch"
Write-Host "Message: $Message"
Write-Host "Staged files:"
$staged | ForEach-Object { Write-Host "  $_" }

if ($DryRun) {
    Write-Host "`nDry run - nothing committed or pushed." -ForegroundColor Yellow
    exit 0
}

git commit -m $Message
if (-not $?) { throw "Commit failed." }

# Publish the branch the first time; plain push afterwards.
git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>$null | Out-Null
if ($?) { git push } else { git push -u origin $branch }
if (-not $?) { throw "Push failed." }

Write-Host "`nPushed $branch to origin." -ForegroundColor Green
