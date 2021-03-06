import {BigNumber} from "ethers/utils";
import {Augur, Provider} from "@augurproject/sdk";
import { ContractDependenciesEthers } from "contract-dependencies-ethers";
import { EthersProvider } from "@augurproject/ethersjs-provider";
import { JsonRpcProvider } from "ethers/providers";
import { Addresses } from "@augurproject/artifacts";

export class API {
  _api:Augur<BigNumber, EthersProvider> | null = null;
  async makeApi(provider:JsonRpcProvider, account:string="") {
    const ethersProvider = new EthersProvider(provider, 10, 0, 40);
    const networkId = await ethersProvider.getNetworkId();
    const contractDependencies = new ContractDependenciesEthers(ethersProvider, undefined, account);

    this._api =  await Augur.create<BigNumber, EthersProvider>(ethersProvider, contractDependencies, Addresses[networkId]);
  }

  get():Augur<BigNumber, EthersProvider> {
    if(this._api) {
      return this._api;
    } else {
      throw new Error("API must be initialized before use.");
    }
  }
}

export const augurApi = new API();
