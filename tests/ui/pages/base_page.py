"""Playwright Page Object Model - Base Page."""

from playwright.async_api import Page, Locator, expect
from typing import Optional


class BasePage:
    """Base page class with common functionality."""

    def __init__(self, page: Page):
        self.page = page

    async def goto(self, url: str, wait_until: str = "networkidle"):
        """Navigate to URL."""
        await self.page.goto(url, wait_until=wait_until)

    async def wait_for_load(self, state: str = "networkidle"):
        """Wait for page load state."""
        await self.page.wait_for_load_state(state)

    async def screenshot(self, path: str, full_page: bool = True):
        """Take screenshot."""
        await self.page.screenshot(path=path, full_page=full_page)

    def get_by_test_id(self, test_id: str) -> Locator:
        """Get element by data-testid attribute."""
        return self.page.locator(f"[data-testid='{test_id}']")

    def get_by_test_id_all(self, test_id: str) -> list[Locator]:
        """Get all elements by data-testid attribute."""
        return self.page.locator(f"[data-testid='{test_id}']").all()

    async def wait_for_element(self, test_id: str, state: str = "visible", timeout: int = 5000):
        """Wait for element to be in state."""
        await expect(self.get_by_test_id(test_id)).to_be_visible(timeout=timeout)

    async def click(self, test_id: str, force: bool = False):
        """Click element by test_id."""
        await self.get_by_test_id(test_id).click(force=force)

    async def fill(self, test_id: str, value: str):
        """Fill input by test_id."""
        await self.get_by_test_id(test_id).fill(value)

    async def get_text(self, test_id: str) -> str:
        """Get text content of element."""
        return await self.get_by_test_id(test_id).inner_text()

    async def get_attribute(self, test_id: str, attr: str) -> Optional[str]:
        """Get attribute of element."""
        return await self.get_by_test_id(test_id).get_attribute(attr)

    async def is_visible(self, test_id: str) -> bool:
        """Check if element is visible."""
        return await self.get_by_test_id(test_id).is_visible()

    async def expect_text_contains(self, test_id: str, text: str, timeout: int = 5000):
        """Expect element to contain text."""
        await expect(self.get_by_test_id(test_id)).to_contain_text(text, timeout=timeout)

    async def expect_not_visible(self, test_id: str, timeout: int = 5000):
        """Expect element to not be visible."""
        await expect(self.get_by_test_id(test_id)).not_to_be_visible(timeout=timeout)

    async def expect_enabled(self, test_id: str, timeout: int = 5000):
        """Expect element to be enabled."""
        await expect(self.get_by_test_id(test_id)).to_be_enabled(timeout=timeout)

    async def expect_disabled(self, test_id: str, timeout: int = 5000):
        """Expect element to be disabled."""
        await expect(self.get_by_test_id(test_id)).to_be_disabled(timeout=timeout)