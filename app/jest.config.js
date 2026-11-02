module.exports = {
  preset: 'jest-expo',
  testTimeout: 30000, // first run compiles everything and can exceed the 5 s default
  testMatch: ['**/__tests__/**/*.test.ts?(x)'],
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@tanstack/.*))',
  ],
};
