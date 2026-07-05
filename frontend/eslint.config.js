module.exports = [
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "commonjs",
      globals: { require: "readonly", module: "readonly", process: "readonly", console: "readonly", __dirname: "readonly" },
    },
    rules: {
      "no-unused-vars": "error",
      "no-undef": "error",
    },
  },
];
