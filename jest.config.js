// For a detailed explanation regarding each configuration property, visit:
// https://jestjs.io/docs/en/configuration.html

// n.b. this cannot be an ES6 module yet — see e.g. https://github.com/facebook/jest/issues/4126

// eslint-disable-next-line no-undef
module.exports = {
    preset: 'jest-puppeteer',

    collectCoverage: true,
    coverageDirectory: 'coverage',
    coveragePathIgnorePatterns: ['/node_modules/'],

    notifyMode: 'failure-change'
};
