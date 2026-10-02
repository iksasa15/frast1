import { test, expect } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const out = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../docs/deck');

test('deck screenshots', async ({ page, request }) => {
  fs.mkdirSync(out, { recursive: true });
  await request.post('/api/demo/reset');
  await page.goto('/');
  await expect(page.getByText('All systems healthy')).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: path.join(out, '01-healthy-map.png'), fullPage: false });

  await page.keyboard.press('Shift+Digit1');
  await expect(page.getByTestId('root-cause')).toContainText('R1 Gi0/0', { timeout: 60_000 });
  await expect.poll(() => page.getByTestId('evidence-item').count()).toBeGreaterThanOrEqual(2);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(out, '08-demo-incident-map.png'), fullPage: false });
  await page.screenshot({ path: path.join(out, 'explain-candidates.png'), fullPage: false });
});
