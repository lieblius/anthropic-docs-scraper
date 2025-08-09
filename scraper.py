#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "aiohttp",
#     "aiolimiter",
# ]
# ///
"""
Anthropic Documentation Scraper

Scrapes URLs from https://docs.anthropic.com/llms.txt and organizes them
hierarchically based on their URL structure.

Usage:
  ./scraper.py --init    # Initial build (creates directory structure)
  ./scraper.py --update  # Update existing files only
"""

import re
import argparse
from pathlib import Path
import aiohttp
from urllib.parse import urlparse
import logging
import asyncio
from aiolimiter import AsyncLimiter
import time
import tarfile
import datetime
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AnthropicDocsScraper:
    def __init__(self, base_dir="docs", requests_per_second=5, cache_hours=1):
        self.base_dir = Path(base_dir)
        self.llms_url = "https://docs.anthropic.com/llms.txt"
        self.rate_limiter = AsyncLimiter(
            requests_per_second, 1.0
        )  # 5 requests per second
        self.cache_seconds = cache_hours * 3600  # Convert hours to seconds

    async def fetch_llms_txt(self):
        """Fetch the llms.txt file and parse URLs"""
        logger.info("Fetching llms.txt...")

        async with aiohttp.ClientSession() as session:
            async with session.get(self.llms_url) as response:
                response.raise_for_status()
                new_text = await response.text()

        # Only save llms.txt if content has changed
        llms_file = Path("llms.txt")
        if llms_file.exists():
            with open(llms_file, "r", encoding="utf-8") as f:
                old_text = f.read()

            if old_text != new_text:
                logger.info("llms.txt content has changed, updating local copy")
                with open(llms_file, "w", encoding="utf-8") as f:
                    f.write(new_text)
            else:
                logger.info("llms.txt content unchanged")
        else:
            logger.info("Creating initial llms.txt")
            with open(llms_file, "w", encoding="utf-8") as f:
                f.write(new_text)

        urls = []
        current_section = ""

        for line in new_text.split("\n"):
            line = line.strip()
            if line.startswith("##"):
                current_section = line[2:].strip().lower().replace(" ", "-")
            elif line.startswith("- [") and "](http" in line:
                match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", line)
                if match:
                    title, url = match.groups()
                    urls.append(
                        {"title": title, "url": url, "section": current_section}
                    )

        logger.info(f"Found {len(urls)} URLs")
        return urls

    def url_to_path(self, url, section=""):
        """Convert URL to local file path"""
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")

        # Remove 'en' language prefix if present
        if path_parts and path_parts[0] == "en":
            path_parts = path_parts[1:]

        # Create directory structure
        if section and section != "docs":
            dir_path = self.base_dir / section / "/".join(path_parts[:-1])
        else:
            dir_path = self.base_dir / "/".join(path_parts[:-1])

        # Get filename
        if path_parts:
            filename = path_parts[-1]
            if not filename.endswith(".md"):
                filename += ".md"
        else:
            filename = "index.md"

        return dir_path / filename

    def is_file_recent(self, file_path):
        """Check if file was downloaded recently (within cache_seconds)"""
        if not file_path.exists():
            return False

        file_age = time.time() - file_path.stat().st_mtime
        return file_age < self.cache_seconds

    def should_do_full_rebuild(self):
        """Check if we should do a full rebuild (backup + clean start)"""
        if not self.base_dir.exists():
            return False

        # Check if llms.txt file has changed (is older than cache time)
        llms_cache_file = Path("llms.txt")
        return not self.is_file_recent(llms_cache_file)

    def backup_docs_folder(self):
        """Create a tar.gz backup of the docs folder"""
        if not self.base_dir.exists():
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"docs_backup_{timestamp}.tar.gz"

        logger.info(f"Creating backup: {backup_name}")

        with tarfile.open(backup_name, "w:gz") as tar:
            tar.add(self.base_dir, arcname=self.base_dir.name)

        logger.info(f"Backup created: {backup_name}")
        return backup_name

    async def download_file(self, url, file_path, session, force=False, max_retries=3):
        """Download a single file asynchronously with rate limiting and retry logic"""
        # Skip if file is recent and not forcing
        if not force and self.is_file_recent(file_path):
            logger.debug(f"Skipping recent file: {file_path}")
            return "cached"

        for attempt in range(max_retries + 1):
            async with self.rate_limiter:
                try:
                    # Add .md extension to URL if not present
                    if not url.endswith(".md"):
                        download_url = url + ".md"
                    else:
                        download_url = url

                    async with session.get(download_url) as response:
                        response.raise_for_status()

                        # Try to decode as text, fall back to binary if needed
                        try:
                            content = await response.text(encoding="utf-8")
                            is_binary = False
                        except UnicodeDecodeError:
                            # Fall back to binary mode for non-text files
                            content = await response.read()
                            is_binary = True

                    # Create directory if it doesn't exist
                    file_path.parent.mkdir(parents=True, exist_ok=True)

                    # Write content based on type
                    if is_binary:
                        with open(file_path, "wb") as f:
                            f.write(content)
                    else:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(content)

                    logger.info(f"Downloaded {download_url} -> {file_path}")
                    return True

                except Exception as e:
                    if attempt < max_retries:
                        # Exponential backoff: 2^attempt seconds
                        wait_time = 2**attempt
                        logger.warning(
                            f"Download failed (attempt {attempt + 1}/{max_retries + 1}): {download_url}: {e}"
                        )
                        logger.info(f"Retrying in {wait_time} seconds...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"Failed to download {download_url} after {max_retries + 1} attempts: {e}"
                        )
                        return False

        return False

    async def init_build_async(self):
        """Initial build - create directory structure and download all files asynchronously"""
        logger.info("Starting initial build...")

        # Check if we need to do a full rebuild (backup + clean start) BEFORE fetching
        should_rebuild = self.should_do_full_rebuild()

        urls = await self.fetch_llms_txt()

        if should_rebuild:
            logger.info("Files need updating - performing full rebuild with backup")
            self.backup_docs_folder()

            # Remove existing docs folder
            if self.base_dir.exists():
                shutil.rmtree(self.base_dir)
                logger.info(f"Removed existing {self.base_dir}")

        # Create base directory
        self.base_dir.mkdir(exist_ok=True)

        async with aiohttp.ClientSession(
            headers={"User-Agent": "AnthropicDocsScraper/1.0"}
        ) as session:
            tasks = []
            for url_info in urls:
                file_path = self.url_to_path(url_info["url"], url_info["section"])
                # Force download since we're doing init (ignore cache logic)
                task = self.download_file(
                    url_info["url"], file_path, session, force=True
                )
                tasks.append(task)

            logger.info(
                f"Downloading {len(tasks)} files with rate limiting (5 req/sec)..."
            )
            results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for result in results if result is True)
        cached_count = sum(1 for result in results if result == "cached")
        fail_count = len(results) - success_count - cached_count

        logger.info(
            f"Initial build complete: {success_count} downloaded, {cached_count} cached, {fail_count} failures"
        )

    def init_build(self):
        """Initial build wrapper"""
        asyncio.run(self.init_build_async())

    async def update_build_async(self):
        """Update existing files without rebuilding directory structure asynchronously"""
        logger.info("Starting update build...")

        if not self.base_dir.exists():
            logger.error("No existing docs directory found. Run with --init first.")
            return

        urls = await self.fetch_llms_txt()

        # Include both existing files AND missing files
        tasks = []

        async with aiohttp.ClientSession(
            headers={"User-Agent": "AnthropicDocsScraper/1.0"}
        ) as session:
            for url_info in urls:
                file_path = self.url_to_path(url_info["url"], url_info["section"])

                if file_path.exists():
                    # Update existing file (respects cache logic)
                    task = self.download_file(url_info["url"], file_path, session)
                    tasks.append(task)
                else:
                    # Download missing file (force download)
                    logger.info(f"Missing file will be downloaded: {file_path}")
                    task = self.download_file(
                        url_info["url"], file_path, session, force=True
                    )
                    tasks.append(task)

            if tasks:
                logger.info(
                    f"Processing {len(tasks)} files (updating existing + downloading missing) with rate limiting (5 req/sec)..."
                )
                results = await asyncio.gather(*tasks, return_exceptions=True)
                success_count = sum(1 for result in results if result is True)
                cached_count = sum(1 for result in results if result == "cached")
                fail_count = len(results) - success_count - cached_count
            else:
                success_count = fail_count = cached_count = 0

        logger.info(
            f"Update complete: {success_count} downloaded/updated, {cached_count} cached, {fail_count} failures"
        )

    def update_build(self):
        """Update build wrapper"""
        asyncio.run(self.update_build_async())


def main():
    parser = argparse.ArgumentParser(description="Anthropic Documentation Scraper")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--init",
        action="store_true",
        help="Initial build (creates directory structure)",
    )
    group.add_argument(
        "--update", action="store_true", help="Update existing files only"
    )

    args = parser.parse_args()

    scraper = AnthropicDocsScraper()

    if args.init:
        scraper.init_build()
    elif args.update:
        scraper.update_build()


if __name__ == "__main__":
    main()
