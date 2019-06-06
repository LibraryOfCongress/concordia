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
});
