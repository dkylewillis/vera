const { writeProCloud } = require('./scripts/write-pro-cloud.cjs');
const { buildConfig } = require('./electron-builder-config.cjs');

writeProCloud();

module.exports = buildConfig(process.env);
