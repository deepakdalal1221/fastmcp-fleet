from __future__ import annotations

import os
from typing import Annotated, Any

from mcp_common.errors import ConfigError, UpstreamError, ValidationError
from pydantic import Field

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    AsyncIOMotorClient = None

_MAX_DOCS = 500


def _uri() -> str:
    raw = os.environ.get("MONGODB_URI", "").strip()
    if not raw:
        raise ConfigError("MONGODB_URI is not set")
    return raw


def _client():
    if AsyncIOMotorClient is None:
        raise ConfigError("motor is not installed; add extras=[db]")
    return AsyncIOMotorClient(_uri(), serverSelectionTimeoutMS=10_000)


def _stringify_id(doc: dict) -> dict:
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def register_tools(mcp) -> None:
    @mcp.tool
    async def find(
        database: Annotated[str, Field(description="Database name")],
        collection: Annotated[str, Field(description="Collection name")],
        filter: Annotated[
            dict[str, Any] | None, Field(description="Mongo filter expression")
        ] = None,
        limit: Annotated[int, Field(description="Max documents returned (1-500)")] = 100,
    ) -> dict:
        """Query documents matching filter; returns up to 500."""
        if not database or not collection:
            raise ValidationError("database and collection are required")
        if not 1 <= limit <= _MAX_DOCS:
            raise ValidationError(f"limit must be between 1 and {_MAX_DOCS}")
        client = _client()
        try:
            cursor = client[database][collection].find(filter or {}).limit(limit)
            docs = [_stringify_id(d) async for d in cursor]
        except Exception as exc:
            raise UpstreamError(f"mongodb find failed: {exc}") from exc
        finally:
            client.close()
        return {"documents": docs, "count": len(docs)}

    @mcp.tool
    async def insert(
        database: Annotated[str, Field(description="Database name")],
        collection: Annotated[str, Field(description="Collection name")],
        document: Annotated[dict[str, Any], Field(description="Document to insert")],
    ) -> dict:
        """Insert one document. Returns the inserted id."""
        if not database or not collection:
            raise ValidationError("database and collection are required")
        if not document:
            raise ValidationError("document must not be empty")
        client = _client()
        try:
            result = await client[database][collection].insert_one(document)
        except Exception as exc:
            raise UpstreamError(f"mongodb insert failed: {exc}") from exc
        finally:
            client.close()
        return {"inserted_id": str(result.inserted_id)}

    @mcp.tool
    async def update(
        database: Annotated[str, Field(description="Database name")],
        collection: Annotated[str, Field(description="Collection name")],
        filter: Annotated[dict[str, Any], Field(description="Mongo filter")],
        update: Annotated[dict[str, Any], Field(description="Update expression (e.g. $set)")],
        upsert: Annotated[bool, Field(description="Insert if not found")] = False,
    ) -> dict:
        """Update the first document matching filter."""
        if not database or not collection:
            raise ValidationError("database and collection are required")
        if not filter or not update:
            raise ValidationError("filter and update must not be empty")
        client = _client()
        try:
            result = await client[database][collection].update_one(filter, update, upsert=upsert)
        except Exception as exc:
            raise UpstreamError(f"mongodb update failed: {exc}") from exc
        finally:
            client.close()
        return {
            "matched": result.matched_count,
            "modified": result.modified_count,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None,
        }

    @mcp.tool
    async def delete(
        database: Annotated[str, Field(description="Database name")],
        collection: Annotated[str, Field(description="Collection name")],
        filter: Annotated[dict[str, Any], Field(description="Mongo filter")],
        many: Annotated[bool, Field(description="Delete all matching (else first)")] = False,
    ) -> dict:
        """Delete document(s) matching filter."""
        if not database or not collection:
            raise ValidationError("database and collection are required")
        if not filter:
            raise ValidationError("filter must not be empty (refusing to delete all)")
        client = _client()
        try:
            coll = client[database][collection]
            result = await (coll.delete_many(filter) if many else coll.delete_one(filter))
        except Exception as exc:
            raise UpstreamError(f"mongodb delete failed: {exc}") from exc
        finally:
            client.close()
        return {"deleted": result.deleted_count}

    @mcp.tool
    async def list_collections(
        database: Annotated[str, Field(description="Database name")],
    ) -> dict:
        """List collections in the given database."""
        if not database:
            raise ValidationError("database is required")
        client = _client()
        try:
            names = await client[database].list_collection_names()
        except Exception as exc:
            raise UpstreamError(f"mongodb list_collections failed: {exc}") from exc
        finally:
            client.close()
        return {"database": database, "collections": sorted(names)}
