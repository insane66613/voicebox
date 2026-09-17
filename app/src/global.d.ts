interface Window {
  __voiceboxServerStartedByApp?: boolean;
  __voiceboxRemoteProxyStartedByApp?: boolean;
}

declare module 'virtual:changelog' {
  const raw: string;
  export default raw;
}
