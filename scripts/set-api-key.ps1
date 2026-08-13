$ErrorActionPreference = "Stop"
$secure = Read-Host "Enter YouTube Data API Key (input is hidden)" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  [Environment]::SetEnvironmentVariable("YOUTUBE_API_KEY", $plain, "User")
  $env:YOUTUBE_API_KEY = $plain
  Write-Host "YOUTUBE_API_KEY saved to the current Windows user environment." -ForegroundColor Green
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
