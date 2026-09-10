#!/usr/bin/env python3
"""Offline fleet planner. This program never connects to or changes a host."""
import argparse
import json
from pathlib import Path


def ordered_services(catalog):
    entries = catalog["services"]
    services = {entry["id"]: entry for entry in entries}
    if len(services) != len(entries):
        raise ValueError("Duplicate service ID")
    pending = {name: set(row.get("depends_on", [])) for name, row in services.items()}
    for name, dependencies in pending.items():
        if dependencies - services.keys() or name in dependencies:
            raise ValueError("Unknown or self dependency: " + name)
    ordered = []
    while pending:
        ready = sorted(name for name, dependencies in pending.items() if not dependencies)
        if not ready:
            raise ValueError("Dependency cycle; no deployment order is inferred")
        for name in ready:
            ordered.append(services[name])
            pending.pop(name)
        for dependencies in pending.values():
            dependencies.difference_update(ready)
    return ordered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).with_name("service-catalog.json"))
    args = parser.parse_args()
    try:
        catalog = json.loads(args.catalog.read_text())
        services = ordered_services(catalog)
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(2, "Invalid catalog: " + str(error) + "\n")
    rows = [{"order": index, "service": row["id"], "unit": row["unit"],
             "manager": row.get("manager", {"scope": "system"}), "runtime": row["runtime"],
             "port": row["port"], "probeStrength": row["probe"]["strength"],
             "effectsRequiringAcknowledgment": row.get("effects", []),
             "script": "scripts/" + row["id"] + ".sh"}
            for index, row in enumerate(services, 1)]
    print(json.dumps({"mode": "plan", "host": catalog["host"], "serviceCount": len(rows),
                      "hostAccessed": False, "deploymentPerformed": False, "services": rows,
                      "exclusions": catalog.get("exclusions", []), "auxiliary": catalog.get("auxiliary", [])}, indent=2))


if __name__ == "__main__":
    main()
