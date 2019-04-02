import { NetworkId } from "@augurproject/artifacts";
import { Abi } from "ethereum";
import { Filter, LogValues, FullLog } from "./types";
import { Log } from "ethers/providers";

export interface Provider {
  getNetworkId(): Promise<NetworkId>;
  getLogs(filter: Filter): Promise<Log[]>;
  getBlockNumber(): Promise<number>;
  storeAbiData(abi: Abi, contractName: string): void;
  getEventTopic(contractName: string, eventName: string): string;
  parseLogValues(contractName: string, log: FullLog): LogValues;
}
