import { Log } from "ethers/providers";

type AllRequired<T> = {
  [P in keyof T]-?: T[P];
};

export type FullLog = AllRequired<Log>;

export interface LogValues {
  [paramName: string]: any;
}

export interface ParsedLog {
  blockNumber?: number;
  blockHash?: string;
  transactionIndex?: number;
  removed?: boolean;
  transactionLogIndex?: number;
  transactionHash?: string;
  logIndex?: number;
  [paramName: string]: any;
}

export interface Filter {
    fromBlock?: number | string;
    toBlock?: number | string;
  address?: string;
  topics?: Array<string | Array<string>>;
}
