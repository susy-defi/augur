import {
  ACCOUNTS,
  compileAndDeployToGanache,
  ContractAPI,
  makeDbMock,
} from "../../libs";
import { UserSyncableDB } from "@augurproject/state/src/db/UserSyncableDB";
import { ContractDependenciesEthers } from "contract-dependencies-ethers";
import {ethers} from "ethers";
import { ContractAddresses } from "@augurproject/artifacts";
import { GenericAugurInterfaces } from "@augurproject/core";
import { EthersProvider } from "@augurproject/ethersjs-provider";
import { DB } from "@augurproject/state/src/db/DB";
import { BlockAndLogStreamerListener } from "@augurproject/state/src/db/BlockAndLogStreamerListener";
import { EventLogDBRouter } from "@augurproject/state/src/db/EventLogDBRouter";
import { stringTo32ByteHex } from "../../libs/Utils";

const mock = makeDbMock();

let addresses: ContractAddresses;
let dependencies: ContractDependenciesEthers;
let provider: EthersProvider;
beforeAll(async () => {
  const result = await compileAndDeployToGanache(ACCOUNTS);
  addresses = result.addresses;
  dependencies = result.dependencies;
  provider = result.provider;
}, 120000);

let john: ContractAPI;
let mary: ContractAPI;
beforeEach(async () => {
  john = await ContractAPI.userWrapper(ACCOUNTS, 0, provider, addresses);
  mary = await ContractAPI.userWrapper(ACCOUNTS, 1, provider, addresses);

  // Use testnet rep token contract since it has faucet().
  john.augur.contracts.setReputationToken("4");
  mary.augur.contracts.setReputationToken("4");

  mock.cancelFail();
  await mock.wipeDB();
});

// UserSyncableDB overrides protected getLogs class, which is only called in sync.
test("sync", async () => {
  await john.approveCentralAuthority();
  await mary.approveCentralAuthority();

  const eventName = "TokensTransferred";
  const sender = ACCOUNTS[0].publicKey;
  const highestAvailableBlockNumber = 0;
  const db = new UserSyncableDB<ethers.utils.BigNumber>(dbController, mock.constants.networkId, eventName, sender, 0, [0]);

  const dbController = await DB.createAndInitializeDB(
    mock.constants.networkId,
    0,
    mock.constants.defaultStartSyncBlockNumber,
    [ john.account, mary.account ],
    john.augur.genericEventNames,
    john.augur.userSpecificEvents,
    mock.makeFactory(),
    blockAndLogStreamerListener,
  );

  await dbController.sync(john.augur, mock.constants.chunkSize, 0);

  blockAndLogStreamerListener.listenForBlockRemoved(dbController.rollback.bind(dbController));
  blockAndLogStreamerListener.startBlockStreamListener();

  // Generate logs to be synced
  const from = john.account;
  const to = mary.account;
  const fromBalance = new ethers.utils.BigNumber(10);
  const value = new ethers.utils.BigNumber(4);

  await john.createReasonableMarket(john.augur.contracts.universe, [stringTo32ByteHex("a"), stringTo32ByteHex("b")]);

  const reputationToken = john.augur.contracts.reputationToken as GenericAugurInterfaces.TestNetReputationToken<ethers.utils.BigNumber>;
  await reputationToken.faucet(fromBalance);
  await provider.provider.send("evm_mine", null);

  await provider.provider.send("evm_mine", null);

  await dbController.sync(john.augur, mock.constants.chunkSize, 0);

  const f = async (account: string) => {
    const tokensTransferredDB = mock.getDatabases()[`db/4-TokensTransferred-${account}`];
    const docs = await tokensTransferredDB.allDocs();

    expect(docs.total_rows).toEqual(2);
    //   expect(docs).toEqual({
    //     offset: 0,
    //     rows: [
    //       { // The default row.
    //         id: "_design/idx-c1ebf959ffec1e6bc1e3bfe00a3f8093",
    //         key: "_design/idx-c1ebf959ffec1e6bc1e3bfe00a3f8093",
    //         value: {
    //           rev: "1-bbd6125c4844759bd4cb7bd5362df937",
    //         },
    //       },
    //       { // The row we just added.
    //         id: "TODO",
    //         key: "TODO",
    //         value: {
    //           rev: "TODO",
    //         },
    //       },
    //     ],
    //     total_rows: 2,
    //   });
  };

  await f(john.account);
  // await f(mary.account);


}, 180000);

// Constructor does some (private) processing, so verify that it works right.
test("props", async () => {
  const dbController = await mock.makeDB(john.augur, ACCOUNTS);

  const eventName = "foo";
  const user = "artistotle";
  const db = new UserSyncableDB<ethers.utils.BigNumber>(dbController, mock.constants.networkId, eventName, user, 2, [0]);

  // @ts-ignore - verify private property "additionalTopics"
  expect(db.additionalTopics).toEqual([
    "0x000000000000000000000000tistotle",
  ]);
});
