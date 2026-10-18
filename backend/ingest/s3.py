"""A company's own S3-compatible bucket (AWS S3, Cloudflare R2, MinIO, ...) that holds its original documents.

KT Brain reads the docs under the configured prefix into the graph (chunks for search, decisions by extraction) and
keeps each one's object key on its Doc node, so a reader can open the original file with its formatting. Originals stay
in the company's bucket: KT Brain stores only the redacted text chunks and the key, and hands out short-lived links.
"""
import boto3
from botocore.config import Config

import extract
from ingest import uploads

DOC_EXT = (".md", ".markdown", ".txt", ".pdf")
MAX_BYTES = 8 * 1024 * 1024  # the same cap as a web upload (app.MAX_UPLOAD)
MAX_FILES = 200  # per import; a bigger bucket is read in several imports (unchanged files are skipped)
LINK_SECONDS = 300
CONTENT_TYPE = {".pdf": "application/pdf", ".md": "text/plain; charset=utf-8", ".markdown": "text/plain; charset=utf-8",
                ".txt": "text/plain; charset=utf-8"}


def client(cfg: dict):
    if cfg.get("endpoint"):
        extract.check_base(cfg["endpoint"])  # an admin sets this URL: public https hosts only, never the server's network
    return boto3.client("s3", endpoint_url=cfg.get("endpoint") or None, region_name=cfg.get("region") or "us-east-1",
                        aws_access_key_id=cfg["key_id"], aws_secret_access_key=cfg["secret"],
                        config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=30,
                                      retries={"max_attempts": 2}))


def prefix(cfg: dict) -> str:
    p = (cfg.get("prefix") or "").strip("/")
    return f"{p}/" if p else ""


def check(cfg: dict):
    """Raises when the bucket can't be reached with these credentials."""
    client(cfg).list_objects_v2(Bucket=cfg["bucket"], Prefix=prefix(cfg), MaxKeys=1)


def put(cfg: dict, name: str, raw: bytes) -> str:
    """Store a web upload's original next to the company's docs; returns its key."""
    key = f"{prefix(cfg)}kt-brain-uploads/{name}"
    client(cfg).put_object(Bucket=cfg["bucket"], Key=key, Body=raw)
    return key


def link(cfg: dict, key: str) -> str:
    """A link to one original that works for LINK_SECONDS, shown inline in the browser."""
    ext = "." + key.rsplit(".", 1)[-1].lower() if "." in key else ""
    params = {"Bucket": cfg["bucket"], "Key": key, "ResponseContentDisposition": "inline"}
    if ext in CONTENT_TYPE:
        params["ResponseContentType"] = CONTENT_TYPE[ext]
    return client(cfg).generate_presigned_url("get_object", Params=params, ExpiresIn=LINK_SECONDS)


def import_docs(g, cfg: dict, person: str, status) -> tuple[list, str]:
    """Read new or changed docs under the prefix into the graph. Returns (refs to extract decisions from, summary)."""
    c, p = client(cfg), prefix(cfg)
    found = []
    for page in c.get_paginator("list_objects_v2").paginate(Bucket=cfg["bucket"], Prefix=p):
        found += [(o["Key"], o["ETag"]) for o in page.get("Contents", [])
                  if o["Key"].lower().endswith(DOC_EXT) and 0 < o["Size"] <= MAX_BYTES]
    known = dict(g.ro_query("MATCH (d:Doc) WHERE d.original IS NOT NULL RETURN d.original, d.etag").result_set)
    todo = [(k, e) for k, e in found if known.get(k) != e][:MAX_FILES]
    refs, failed = [], 0
    for i, (key, etag) in enumerate(todo):
        status(f"reading {i + 1}/{len(todo)}: {key}")
        try:
            kind, text = uploads.parse_upload(key.rsplit("/", 1)[-1], c.get_object(Bucket=cfg["bucket"], Key=key)["Body"].read())
        except Exception:  # an unreadable PDF: skip it, keep importing the rest
            failed += 1
            continue
        refs.append(uploads.add_doc(g, person, key.rsplit("/", 1)[-1], text, did=f"s3/{key}", original=key, etag=etag))
    left = len([1 for k, e in found if known.get(k) != e]) - len(todo)
    summary = (f"done: {len(refs)} documents read, {len(found) - len(todo) - left} unchanged"
               + (f", {failed} unreadable" if failed else "") + (f", {left} more next import" if left else ""))
    return refs, summary
