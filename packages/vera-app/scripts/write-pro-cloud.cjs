const fs = require('fs');
const path = require('path');

function writeProCloud() {
  const out = path.join(__dirname, '..', 'build', 'pro-cloud.json');
  const config = {
    siteUrl: process.env.VERA_PRO_SITE_URL || '',
    supabaseUrl: process.env.VERA_PRO_SUPABASE_URL || '',
    supabaseAnonKey: process.env.VERA_PRO_SUPABASE_ANON_KEY || '',
  };
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, `${JSON.stringify(config, null, 2)}\n`);
  return out;
}

if (require.main === module) {
  writeProCloud();
}

module.exports = { writeProCloud };
