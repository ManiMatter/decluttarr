const { execSync } = require('child_process');

// Function to execute shell commands
function execute(command) {
  return execSync(command, { encoding: 'utf-8' });
}

// Get all package versions from GitHub Packages registry
const packageVersions = execute('npm show @manimatter/decluttarr versions --registry=https://npm.pkg.github.com');

// Get all tagged versions
const taggedVersions = execute('git tag').split('\n');

// Get all referenced versions
const referencedVersions = execute('npm view @manimatter/decluttarr dependencies --json --registry=https://npm.pkg.github.com');

// Logic to find untagged and unreferenced versions
const untaggedAndUnreferencedVersions = packageVersions.filter(version => {
  // Check if version is not tagged
  const isUntagged = !taggedVersions.includes(version.trim());

  // Check if version is not referenced by another package
  const isUnreferenced = !Object.values(referencedVersions).flat().includes(version.trim());

  return isUntagged && isUnreferenced;
});

console.log('Untagged and Unreferenced Versions:', untaggedAndUnreferencedVersions);
