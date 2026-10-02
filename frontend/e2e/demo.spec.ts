import { test, expect } from '@playwright/test';

for (const run of [1, 2, 3]) {
  test(`full demo loop — run ${run}`, async ({ page, request }) => {
    await request.post('/api/demo/reset');
    await page.goto('/');
    await expect(page.getByText('All systems healthy')).toBeVisible({ timeout: 30_000 });

    await page.keyboard.press('Shift+Digit1');
    await expect(page.getByTestId('root-cause')).toContainText('R1 Gi0/0', { timeout: 60_000 });
    await expect.poll(() => page.getByTestId('evidence-item').count()).toBeGreaterThanOrEqual(2);

    await page.getByRole('button', { name: 'Reject' }).click();
    await page.getByPlaceholder('Outside change window').fill('Outside change window');
    await page.getByRole('button', { name: 'Confirm reject' }).click();
    await expect(page.getByTestId('timeline')).toContainText('Rejected');

    await expect(page.getByRole('button', { name: 'Approve Remediation' })).toBeEnabled();
    await page.getByRole('button', { name: 'Approve Remediation' }).click();
    await expect(page.getByTestId('incident-status')).toHaveText(/resolved/i, { timeout: 90_000 });
  });
}
