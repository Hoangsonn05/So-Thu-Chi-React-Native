const { getDefaultConfig, mergeConfig } = require('@react-native/metro-config');
const { getDefaultConfig: getExpoDefaultConfig } = require('expo/metro-config');

/**
 * Metro configuration
 * https://reactnative.dev/docs/metro
 *
 * @type {import('metro-config').MetroConfig}
 */
const expoConfig = getExpoDefaultConfig(__dirname);
const rnConfig = getDefaultConfig(__dirname);

const config = mergeConfig(rnConfig, expoConfig);

module.exports = config;
