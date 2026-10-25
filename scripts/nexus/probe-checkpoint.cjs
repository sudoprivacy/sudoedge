// Read-only product qualification, not a second Agent runtime or sender.
const fs = require('node:fs');
const { createRequire } = require('node:module');
const crypto = require('node:crypto');
function inspectRecords(records, profile, mode) {
  if (![undefined,'--baseline','--live-agent','--existing-agent'].includes(mode)) throw Error('Unknown native observation mode');
  if (!Array.isArray(records)) throw Error('Native Agent directory is not an array');
  const managed = records.filter(record => record.kind === 'MANAGED');
  const active = managed.filter(record => record.state !== 'TERMINATED');
  const live = mode === '--live-agent';
  const existing = mode === '--existing-agent';
  if (live || existing) {
    if (!managed.length || active.length > 1 || (live && active.length !== 1) ||
        managed.some(record => record.name !== profile.expectedLiveAgentId || record.owner_id !== profile.expectedLiveOwnerId)) {
      throw Error('Existing Agent identity or active execution count differs: '+JSON.stringify(managed.map(record => ({
        pid:record.pid,agentId:record.name,ownerId:record.owner_id,state:record.state,zone:record.zone_id}))));
    }
  } else {
    if (mode !== '--baseline' && managed.length !== profile.expectedManagedCount) throw Error('Agent process count differs from the restored original runtime baseline');
    if (active.length) throw Error('Unexpected live managed Agent');
  }
  const canonical = managed.map(record => JSON.stringify([record.name,record.owner_id,record.zone_id,record.state])).sort();
  const identityHash = crypto.createHash('sha256').update(JSON.stringify(canonical)).digest('hex');
  if (!live && !existing && mode !== '--baseline' && identityHash !== profile.expectedManagedIdentitySha256) throw Error('Agent process bindings differ from the restored original runtime baseline');
  const selected = active[0] || managed[0];
  return {authenticatedNodeControl:true,managedCount:managed.length,activeManagedCount:active.length,
    historicalTerminatedCount:managed.length-active.length,managedIdentitySha256:identityHash,
    ...(live || existing ? {existingExecution:{agentId:selected.name,ownerId:selected.owner_id,state:selected.state,zone:selected.zone_id},executionActive:active.length===1} : {}),
    newAgentCreated:false,inferenceRequested:false};
}

function main() {
  const profile = JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
  const clientRequire = createRequire(profile.grpcPackageJson);
  const grpc = clientRequire('@grpc/grpc-js');
  const loader = clientRequire('@grpc/proto-loader');
  const proto = loader.loadSync(profile.protoRoot+'/nexus/grpc/vfs/vfs.proto',{
    keepCase:true,longs:String,defaults:true,includeDirs:[profile.protoRoot]});
  const Api = grpc.loadPackageDefinition(proto).nexus.grpc.vfs.NexusVFSService;
  const tls = profile.tls;
  const client = new Api(profile.bind,grpc.credentials.createSsl(fs.readFileSync(tls.ca),fs.readFileSync(tls.key),fs.readFileSync(tls.cert)),{
    'grpc.ssl_target_name_override':tls.serverName,'grpc.default_authority':tls.serverName});
  client.Call({method:'agent_list',payload:Buffer.from('{}'),auth_token:''},{deadline:Date.now()+8000},(error,reply)=>{
    try {
      if (error) throw error;
      if (reply.is_error) throw Error('Native agent_list was rejected');
      console.log(JSON.stringify(inspectRecords(JSON.parse(Buffer.from(reply.payload).toString()).result,profile,process.argv[3])));
    } catch (failure) {console.error(failure.message);process.exitCode=1;}
    finally {client.close();}
  });
}

module.exports = {inspectRecords};
if (require.main === module) main();
