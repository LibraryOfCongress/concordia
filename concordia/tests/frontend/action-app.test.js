/* global actionApp */

require('dotenv').config();

describe('action-app', () => {
    beforeEach(async () => {
        await page.goto('http://localhost:8000/account/login/?next=/act/');
        await page.type('#id_username', process.env.TEST_USERNAME);
        await page.type('#id_password', process.env.TEST_PASSWORD);
        await page.click('[type=submit]');
        await page.waitForNavigation();
    });

    it('The page should have a basic title', async () => {
        await expect(page.title()).resolves.toMatch('Crowd: By the People');
    });

    it('The page define the actionApp object', async () => {
        const result = await page.evaluate(() => {
            return 'actionApp' in window;
        });
        expect(result).toBeTruthy();
    });

    it('The actionApp should load data', async () => {
        await Promise.all([
            page.waitForRequest(request => request.url().includes('/review/')),
            page.evaluate(() => actionApp.fetchAssetData())
        ]);
        const loadedAssetCount = await page.evaluate(
            () => actionApp.assets.size
        );
        expect(loadedAssetCount).toBeGreaterThan(0);
    });

    it('The actionApp should connect a web socket', async () => {
        await page.waitForRequest(request =>
            request.url().includes('/ws/asset/asset_updates/')
        );
    });
});
