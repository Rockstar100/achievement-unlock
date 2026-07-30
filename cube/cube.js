const CLICKHOUSE_HOST = process.env.CUBEJS_DB_HOST || 'localhost';
const CLICKHOUSE_PORT = process.env.CUBEJS_DB_PORT || '8123';
const CLICKHOUSE_USER = process.env.CUBEJS_DB_USER || 'default';
const CLICKHOUSE_PASS = process.env.CUBEJS_DB_PASS || '';
const CLICKHOUSE_DB = process.env.CUBEJS_DB_NAME || 'default';

module.exports = {
  reactStrictMode: true,
};

module.exports.dataSource = 'default';

module.exports.driverFactory = () => ({
  type: 'clickhouse',
  host: CLICKHOUSE_HOST,
  port: CLICKHOUSE_PORT,
  user: CLICKHOUSE_USER,
  password: CLICKHOUSE_PASS,
  database: CLICKHOUSE_DB,
});
