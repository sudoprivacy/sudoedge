/** Restore the appliance model route after Nexus starts or Router credentials change. */
import fs from 'node:fs';
import path from 'node:path';
import grpc from '@grpc/grpc-js';
import protoLoader from '@grpc/proto-loader';

const configPath = process.env.SUDOEDGE_MODEL_MOUNT_CONFIG;
if (!configPath) throw new Error('SUDOEDGE_MODEL_MOUNT_CONFIG is required');
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
const router = JSON.parse(fs.readFileSync(config.routerConfig, 'utf8')).auth_modes['api-key'].sudorouter;
if (!router?.baseUrl || !router.apiKey) throw new Error('Provision the local Router before mounting its model route');
const definitions = protoLoader.loadSync(path.join(config.protoRoot, 'nexus/grpc/vfs/vfs.proto'), {
  keepCase: true, longs: String, defaults: true, includeDirs: [config.protoRoot],
});
const api = grpc.loadPackageDefinition(definitions).nexus.grpc.vfs.NexusVFSService;
const credentials = grpc.credentials.createSsl(
  fs.readFileSync(path.join(config.tlsDir, 'ca.pem')),
  fs.readFileSync(path.join(config.tlsDir, 'node-key.pem')),
  fs.readFileSync(path.join(config.tlsDir, 'node.pem')),
);
const client = new api(config.endpoint, credentials, {
  'grpc.ssl_target_name_override': 'nexus-node', 'grpc.default_authority': 'nexus-node',
});
try {
  await new Promise((resolve, reject) => client.waitForReady(Date.now() + 60000, error => error ? reject(error) : resolve()));
  const result = await new Promise((resolve, reject) => client.Setattr({
    path: config.mountPath, entry_type: 2, backend_type: 'openai', backend_name: 'edge-router',
    zone_id: config.zoneId,
    backend_params: { base_url: router.baseUrl, api_key: router.apiKey, blob_root: config.blobRoot },
  }, { deadline: Date.now() + 90000 }, (error, reply) => error ? reject(error) : resolve(reply)));
  if (result.is_error) throw new Error('Nexus rejected model mount configuration');
  console.log(`Nexus model route ready: ${config.mountPath} -> local Router`);
} finally {
  client.close();
}
