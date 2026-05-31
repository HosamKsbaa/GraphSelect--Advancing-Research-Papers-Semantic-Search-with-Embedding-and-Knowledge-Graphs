# Dump all container logs to the logs/ directory
New-Item -ItemType Directory -Path "logs" -ErrorAction SilentlyContinue

$services = "frontend", "api", "neo4j", "mysql", "mitmproxy"

Write-Host "Dumping logs from dev containers into logs/ folder..."
foreach ($s in $services) {
    Write-Host " -> Writing logs/$s.log"
    docker-compose -f docker-compose.dev.yml logs $s > "logs/$s.log"
}

Write-Host "Logs dumped successfully!"
