describe('contact-us', () => {
    beforeEach(async () => {
        await page.goto('http://localhost:8000/contact/');
    });

    it('The page should have the expected title', async () => {
        await expect(page.title()).resolves.toMatch('Crowd: Contact Us');
    });

    it('The contact form should not be valid by default', async () => {
        const contactForm = await expect(page).toMatchElement(
            '#contact-form:invalid'
        );
        await expect(contactForm).toClick('[type="submit"]');
        await expect(page).toMatchElement(
            '#contact-form.was-validated:invalid'
        );
    });

    it('The contact form should become valid after filling', async () => {
        await expect(page).toFillForm('#contact-form:invalid', {
            email: 'test@example.com',
            story: 'test message',
            subject: 'test subject'
        });
        await expect(page).toMatchElement('#contact-form:valid');
    });
});
