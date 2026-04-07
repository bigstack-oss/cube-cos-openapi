#!/usr/bin/env python3
"""Split monolithic docs.yaml into multi-file OpenAPI structure under src/."""

import copy
import os
import re
import sys
from collections import OrderedDict

import yaml


# Preserve key ordering
class OrderedDumper(yaml.SafeDumper):
    pass


def _dict_representer(dumper, data):
    return dumper.represent_mapping(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, data.items())


OrderedDumper.add_representer(OrderedDict, _dict_representer)
OrderedDumper.add_representer(dict, _dict_representer)


# Preserve literal block scalars
class LiteralStr(str):
    pass


def _literal_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


OrderedDumper.add_representer(LiteralStr, _literal_representer)


class OrderedLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader, node):
    loader.flatten_mapping(node)
    return OrderedDict(loader.construct_pairs(node))


OrderedLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


# Tag-to-filename mapping
TAG_TO_FILE = {
    "Logout": "logout",
    "User Info": "me",
    "Data Centers": "datacenters",
    "Services": "services",
    "Events": "events",
    "Notifications": "notifications",
    "Health": "healths",
    "Integrations": "integrations",
    "Licenses": "licenses",
    "Metrics": "metrics",
    "Nodes": "nodes",
    "Settings": "settings",
    "Tokens": "tokens",
    "Tunings": "tunings",
    "Triggers": "triggers",
    "Support Files": "supportFiles",
    "Grafana": "grafana",
    "OpenSearch": "opensearch",
    "Images": "images",
    "Volumes": "volumes",
    "Firmwares": "firmwares",
    "Fixpacks": "fixpacks",
}


def write_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, Dumper=OrderedDumper, default_flow_style=False, allow_unicode=True, sort_keys=False)


def rewrite_refs(obj, ref_rewriter, parent_key=None):
    """Recursively rewrite $ref values and discriminator mapping values."""
    if isinstance(obj, dict):
        new = OrderedDict()
        for k, v in obj.items():
            if k == "$ref" and isinstance(v, str) and v.startswith("#/components/"):
                new[k] = ref_rewriter(v)
            elif parent_key == "mapping" and isinstance(v, str) and v.startswith("#/components/"):
                new[k] = ref_rewriter(v)
            else:
                new[k] = rewrite_refs(v, ref_rewriter, parent_key=k)
        return new
    elif isinstance(obj, list):
        return [rewrite_refs(item, ref_rewriter, parent_key=parent_key) for item in obj]
    return obj


def schema_ref_rewriter(ref):
    """Rewrite refs for use inside schema files (same directory)."""
    m = re.match(r"#/components/schemas/(.+)", ref)
    if m:
        return f"./{m.group(1)}.yaml"
    m = re.match(r"#/components/parameters/(.+)", ref)
    if m:
        return f"../parameters/{m.group(1)}.yaml"
    m = re.match(r"#/components/requestBodies/(.+)", ref)
    if m:
        return f"../requestBodies/{m.group(1)}.yaml"
    return ref


def parameter_ref_rewriter(ref):
    """Rewrite refs for use inside parameter files."""
    m = re.match(r"#/components/schemas/(.+)", ref)
    if m:
        return f"../schemas/{m.group(1)}.yaml"
    m = re.match(r"#/components/parameters/(.+)", ref)
    if m:
        return f"./{m.group(1)}.yaml"
    return ref


def request_body_ref_rewriter(ref):
    """Rewrite refs for use inside requestBodies files."""
    m = re.match(r"#/components/schemas/(.+)", ref)
    if m:
        return f"../schemas/{m.group(1)}.yaml"
    return ref


def path_ref_rewriter(ref):
    """Rewrite refs for use inside path files (now 2 levels deep: paths/{tag}/)."""
    m = re.match(r"#/components/schemas/(.+)", ref)
    if m:
        return f"../../components/schemas/{m.group(1)}.yaml"
    m = re.match(r"#/components/parameters/(.+)", ref)
    if m:
        return f"../../components/parameters/{m.group(1)}.yaml"
    m = re.match(r"#/components/requestBodies/(.+)", ref)
    if m:
        return f"../../components/requestBodies/{m.group(1)}.yaml"
    return ref


def get_tag_for_path(path_data):
    """Extract the first tag from a path's operations."""
    for method in ["get", "post", "put", "patch", "delete", "head", "options"]:
        if method in path_data:
            tags = path_data[method].get("tags", [])
            if tags:
                return tags[0]
    return None


# Base path prefixes for each tag, used to derive short filenames
TAG_BASE_PATH = {
    "logout": "/api/v1",
    "me": "/api/v1/datacenters/{dataCenter}",
    "datacenters": "/api/v1",
    "services": "/api/v1/datacenters/{dataCenter}",
    "events": "/api/v1/datacenters/{dataCenter}",
    "notifications": "/api/v1/datacenters/{dataCenter}",
    "healths": "/api/v1/datacenters/{dataCenter}",
    "integrations": "/api/v1/datacenters/{dataCenter}",
    "licenses": "/api/v1/datacenters/{dataCenter}",
    "metrics": "/api/v1/datacenters/{dataCenter}",
    "nodes": "/api/v1/datacenters/{dataCenter}",
    "settings": "/api/v1/datacenters/{dataCenter}",
    "tokens": "/api/v1/datacenters/{dataCenter}",
    "tunings": "/api/v1/datacenters/{dataCenter}",
    "triggers": "/api/v1/datacenters/{dataCenter}",
    "supportFiles": "/api/v1/datacenters/{dataCenter}",
    "grafana": "/api/v1/datacenters/{dataCenter}",
    "opensearch": "/api/v1/datacenters/{dataCenter}",
    "images": "/api/v1/datacenters/{dataCenter}",
    "volumes": "/api/v1/datacenters/{dataCenter}",
    "firmwares": "/api/v1/datacenters/{dataCenter}",
    "fixpacks": "/api/v1/datacenters/{dataCenter}",
}


def path_to_filename(path_key, tag_dir):
    """Derive a short filename from a path key by stripping the common prefix."""
    base = TAG_BASE_PATH.get(tag_dir, "/api/v1/datacenters/{dataCenter}")
    suffix = path_key
    if path_key.startswith(base):
        suffix = path_key[len(base):]
    suffix = suffix.lstrip("/")
    if not suffix:
        # Root path for this tag, shouldn't happen but handle gracefully
        suffix = tag_dir
    # Replace {param} with {param}, / with _, .csv etc kept
    suffix = suffix.replace("/", "_")
    return suffix


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_path = os.path.join(base_dir, "docs.yaml")
    src_dir = os.path.join(base_dir, "src")

    print(f"Reading {docs_path}...")
    with open(docs_path) as f:
        doc = yaml.load(f, Loader=OrderedLoader)

    components = doc.get("components", {})
    schemas = components.get("schemas", {})
    parameters = components.get("parameters", {})
    request_bodies = components.get("requestBodies", {})
    security_schemes = components.get("securitySchemes", {})
    paths = doc.get("paths", {})

    # --- Extract schemas ---
    print(f"Extracting {len(schemas)} schemas...")
    for name, schema in schemas.items():
        schema_rewritten = rewrite_refs(copy.deepcopy(schema), schema_ref_rewriter)
        write_yaml(os.path.join(src_dir, "components", "schemas", f"{name}.yaml"), schema_rewritten)

    # --- Extract parameters ---
    print(f"Extracting {len(parameters)} parameters...")
    for name, param in parameters.items():
        param_rewritten = rewrite_refs(copy.deepcopy(param), parameter_ref_rewriter)
        write_yaml(os.path.join(src_dir, "components", "parameters", f"{name}.yaml"), param_rewritten)

    # --- Extract request bodies ---
    print(f"Extracting {len(request_bodies)} request bodies...")
    for name, body in request_bodies.items():
        body_rewritten = rewrite_refs(copy.deepcopy(body), request_body_ref_rewriter)
        write_yaml(os.path.join(src_dir, "components", "requestBodies", f"{name}.yaml"), body_rewritten)

    # --- Extract security schemes ---
    print(f"Extracting {len(security_schemes)} security schemes...")
    for name, scheme in security_schemes.items():
        write_yaml(os.path.join(src_dir, "components", "securitySchemes", f"{name}.yaml"), scheme)

    # --- Extract paths grouped by tag, one file per path ---
    print(f"Extracting {len(paths)} paths into per-tag directories...")
    tag_paths = OrderedDict()  # tag_dir -> [(path_key, filename, path_data)]
    for path_key, path_data in paths.items():
        tag = get_tag_for_path(path_data)
        if tag is None:
            print(f"  WARNING: No tag found for path {path_key}, skipping")
            continue
        tag_dir = TAG_TO_FILE.get(tag)
        if tag_dir is None:
            print(f"  WARNING: Unknown tag '{tag}' for path {path_key}, skipping")
            continue
        if tag_dir not in tag_paths:
            tag_paths[tag_dir] = []
        path_rewritten = rewrite_refs(copy.deepcopy(path_data), path_ref_rewriter)
        filename = path_to_filename(path_key, tag_dir)
        tag_paths[tag_dir].append((path_key, filename, path_rewritten))

    total_path_files = 0
    for tag_dir, entries in tag_paths.items():
        for path_key, filename, path_data in entries:
            write_yaml(os.path.join(src_dir, "paths", tag_dir, f"{filename}.yaml"), path_data)
            total_path_files += 1
        print(f"  {tag_dir}/: {len(entries)} paths")

    # --- Generate root openapi.yaml ---
    print("Generating src/openapi.yaml...")
    root = OrderedDict()
    root["openapi"] = doc["openapi"]
    root["info"] = doc["info"]

    # Paths with $ref to individual files
    root_paths = OrderedDict()
    for path_key, path_data in paths.items():
        tag = get_tag_for_path(path_data)
        tag_dir = TAG_TO_FILE.get(tag)
        filename = path_to_filename(path_key, tag_dir)
        root_paths[path_key] = {"$ref": f"./paths/{tag_dir}/{filename}.yaml"}
    root["paths"] = root_paths

    # Components with $ref
    root_components = OrderedDict()

    root_components["securitySchemes"] = OrderedDict()
    for name in security_schemes:
        root_components["securitySchemes"][name] = {"$ref": f"./components/securitySchemes/{name}.yaml"}

    root_components["parameters"] = OrderedDict()
    for name in parameters:
        root_components["parameters"][name] = {"$ref": f"./components/parameters/{name}.yaml"}

    root_components["schemas"] = OrderedDict()
    for name in schemas:
        root_components["schemas"][name] = {"$ref": f"./components/schemas/{name}.yaml"}

    root_components["requestBodies"] = OrderedDict()
    for name in request_bodies:
        root_components["requestBodies"][name] = {"$ref": f"./components/requestBodies/{name}.yaml"}

    root["components"] = root_components

    # Security
    if "security" in doc:
        root["security"] = doc["security"]

    write_yaml(os.path.join(src_dir, "openapi.yaml"), root)

    print(f"\nDone! Files written to {src_dir}/")
    print(f"  - 1 root openapi.yaml")
    print(f"  - {total_path_files} path files in {len(tag_paths)} directories")
    print(f"  - {len(schemas)} schema files")
    print(f"  - {len(parameters)} parameter files")
    print(f"  - {len(request_bodies)} request body files")
    print(f"  - {len(security_schemes)} security scheme files")
    print(f"  Total: {1 + total_path_files + len(schemas) + len(parameters) + len(request_bodies) + len(security_schemes)} files")


if __name__ == "__main__":
    main()
