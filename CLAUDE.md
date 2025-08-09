# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a Python-based documentation scraper that fetches and organizes Anthropic's documentation from their llms.txt file. The tool creates a hierarchical mirror of their docs with smart caching and rate limiting.

## Development Commands

Use the `justfile` for all common operations:

- `just init` - Initial build (downloads all documentation, creates directory structure)
- `just update` - Update existing files and download any missing ones  
- `just check` - Run ruff linting with automatic fixes
- `just format` - Run ruff code formatting
- `just codeql` - Run both linting and formatting together

Direct script usage:
- `uv run scraper.py --init` - Direct initial build
- `uv run scraper.py --update` - Direct update mode

## Architecture

### Core Components

**AnthropicDocsScraper Class** (`scraper.py`)
- Main orchestrator with async HTTP client and rate limiting
- Configurable: `requests_per_second=5`, `cache_hours=1`
- Handles both binary and text file downloads with encoding fallback

**Key Methods:**
- `fetch_llms_txt()` - Downloads and parses the source URL list, only updates local copy when content changes
- `url_to_path()` - Converts URLs to hierarchical file paths (removes `/en/` prefix, groups by sections)
- `download_file()` - Async download with exponential backoff retry (3 attempts: 1s, 2s, 4s delays)

### Smart Caching Strategy

**File Age Checking**: Files are considered "recent" for 1 hour after download
**Content-Based Updates**: llms.txt is only saved when content actually changes (prevents false rebuilds)
**Backup Logic**: When llms.txt changes during `--init`, automatically creates timestamped tar.gz backup before rebuild

### Operation Modes

**Init Mode (`--init`)**:
- Checks if llms.txt has changed → triggers backup + clean rebuild if needed
- Force downloads all files (ignores cache)
- Creates fresh directory structure

**Update Mode (`--update`)**:
- Downloads missing files (force=True)  
- Updates existing files (respects 1-hour cache)
- Ideal for recovering from partial failures or getting new content

### Rate Limiting & Reliability

**AsyncLimiter**: 5 requests/second throughput control
**Retry Logic**: Exponential backoff for transient failures (429 errors, network issues)
**Encoding Handling**: Automatic fallback from UTF-8 text to binary mode for PDFs/system cards

## Project Structure

- `scraper.py` - Main executable script (uv inline format)
- `justfile` - Command shortcuts for development
- `llms.txt` - Cached copy of source URL list (for change detection)
- `docs/` - Downloaded documentation hierarchy
- `docs_backup_*.tar.gz` - Automatic backups when rebuilding

The docs directory mirrors Anthropic's URL structure with sections like `api/`, `docs/`, `resources/`, etc.