// Read-only product qualification, not a second Agent runtime or sender.
const fs = require('node:fs');
const { createRequire } = require('node:module');
const crypto = require('node:crypto');
const profile = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const clientRequire = createRequire(profile.grpcPackageJson);
const grpc = clientRequire('@grpc/grpc-js');
const loader = clientRequire('@grpc/proto-loader');
const proto = loader.loadSync(profile.protoRoot+'/nexus/grpc/vfs/vfs.proto', {
  keepCase:true, longs:String, defaults:true, includeDirs:[profile.protoRoot],
});
const Api = grpc.loadPackageDefinition(proto).nexus.grpc.vfs.NexusVFSService;
const tls = profile.tls;
const client = new Api(profile.bind, grpc.credentials.createSsl(
  fs.readFileSync(tls.ca), fs.readFileSync(tls.key), fs.readFileSync(tls.cert)), {
  'grpc.ssl_target_name_override':tls.serverName,
  'grpc.default_authority':tls.serverName,
});
client.Call({method:'agent_list',payload:Buffer.from('{}'),auth_token:''},
  {deadline:Date.now()+8000}, (error, reply) => {
    try {
      if (error) throw error;
      if (reply.is_error) throw Error('Native agent_list was rejected');
      const records = JSON.parse(Buffer.from(reply.payload).toString()).result;
      if (!Array.isArray(records)) throw Error('Native Agent directory is not an array');
      const managed = records.filter(record => record.kind === 'MANAGED');
      const live = process.argv[3] === '--live-agent';
      if (live) {
        if (managed.length !== 1 || managed[0].state === 'TERMINATED' ||
            managed[0].name !== profile.expectedLiveAgentId || managed[0].owner_id !== profile.expectedLiveOwnerId) {
          const observed = records.map(record => ({pid:record.pid,agentId:record.name,ownerId:record.owner_id,
            kind:record.kind,state:record.state,zone:record.zone_id}));
          throw Error('Existing live Agent execution does not match the preserved owner/Agent binding: '+JSON.stringify(observed));
        }
      } else if (process.argv[3] !== '--baseline' && managed.length !== profile.expectedManagedCount) {
        throw Error('Agent process count differs from the restored original runtime baseline');
      }
      if (!live && managed.some(record => record.state !== 'TERMINATED')) throw Error('Unexpected live managed Agent');
      const canonical = managed.map(record => JSON.stringify([record.name,record.owner_id,record.zone_id,record.state])).sort();
      const identityHash = crypto.createHash('sha256').update(JSON.stringify(canonical)).digest('hex');
      if (!live && process.argv[3] !== '--baseline' && identityHash !== profile.expectedManagedIdentitySha256) {
        throw Error('Agent process bindings differ from the restored original runtime baseline');
      }
      console.log(JSON.stringify({authenticatedNodeControl:true, managedCount:managed.length,
        managedIdentitySha256:identityHash,
        ...(live ? { existingExecution:{ agentId:managed[0].name,ownerId:managed[0].owner_id,
          state:managed[0].state,zone:managed[0].zone_id } } : {}),
        newAgentCreated:false, inferenceRequested:false}));
    } catch (failure) {
      console.error(failure.message);
      process.exitCode = 1;
    } finally { client.close(); }
  });
