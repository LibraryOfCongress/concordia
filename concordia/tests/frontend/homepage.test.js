describe('homepage', () => {
    beforeEach(async () => {
        await page.goto('http://localhost:8000/');
    });

    it('The page should have a basic title', async () => {
        await expect(page.title()).resolves.toMatch('Crowd: Home');
    });
});
